import os
import json
import ast
import asyncio
from typing import Dict, Any, List, Optional
from openai import OpenAI
from app.memory.service import MemoryService
from app.tools.flights import search_flights
from app.tools.hotels import search_hotels
from app.tools.activities import suggest_activities
from app.schemas import Action, MemoryDiff
from app.utils import parse_date_flexible
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import asyncio

class Orchestrator:
    def __init__(self):
        self.memory = MemoryService()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    def _build_summarizer_prompt(self, previous_summary: str, last_turns: List[Dict[str, str]], user_message: str, assistant_reply: str, actions: List[Action]) -> List[Dict[str, str]]:
        compact_actions = []
        for a in actions[-5:]:
            try:
                compact_actions.append({
                    "tool": a.tool,
                    "input": a.input,
                    "ok": a.error is None
                })
            except Exception:
                continue
        
        return [
            {
                "role": "system",
                "content": (
                    "You maintain a compact JSON summary of a user's travel planning conversation. "
                    "Rules: Only output JSON (no extra text), keep under ~400 tokens, do not invent facts. "
                    "Use fields: destinations (array of city strings), date_ranges (array of {from,to}), nights (int|null), "
                    "budget_inr_per_night (number|null), interests (array), flight_constraints (object), "
                    "hotel_constraints (object), open_questions (array of strings), next_required_slots (array). "
                    "IMPORTANT: Extract destinations from tool calls (search_flights.to_city, search_hotels.city, suggest_activities.city). "
                    "Example: If actions show search_hotels(city='Paris'), add 'Paris' to destinations array."
                )
            },
            {
                "role": "user",
                "content": json.dumps({
                    "previous_summary": previous_summary or "",
                    "last_turns": last_turns[-10:],
                    "new_turn": {"user": user_message, "assistant": assistant_reply},
                    "actions": compact_actions
                })
            }
        ]
    
    def _safe_json(self, text: str, fallback: str) -> str:
        try:
            obj = json.loads(text)
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = text[start:end+1]
                try:
                    obj = json.loads(candidate)
                    return json.dumps(obj, ensure_ascii=False)
                except Exception:
                    pass
            return fallback or "{}"
    
    def _extract_city_from_summary(self, summary: str) -> Optional[str]:
        """Extract destination city from conversation summary."""
        if not summary:
            return None
        try:
            summary_obj = json.loads(summary)
            destinations = summary_obj.get("destinations", [])
            if destinations and isinstance(destinations, list) and len(destinations) > 0:
                # Return the first destination (most recent/primary)
                return destinations[0] if isinstance(destinations[0], str) else destinations[0].get("city") if isinstance(destinations[0], dict) else None
        except Exception:
            pass
        return None
    
    def _validate_slots(self, tool_name: str, tool_args: Dict[str, Any], profile: Dict[str, Any], summary: str = None) -> Optional[str]:
        """Validate critical slots before tool execution. Returns error message if validation fails."""
        if tool_name == "search_flights":
            if not tool_args.get("from_city") or not tool_args.get("to_city"):
                return "I need to know your departure and destination cities. Which cities would you like to travel between?"
            if not tool_args.get("depart_date"):
                return "I need your travel dates. When would you like to depart?"
        elif tool_name == "search_hotels":
            if not tool_args.get("city"):
                # Try to extract from summary before asking user
                city_from_summary = self._extract_city_from_summary(summary) if summary else None
                if city_from_summary:
                    # Auto-fill the city from summary
                    tool_args["city"] = city_from_summary
                    return None  # Validation passes now
                return "I need to know which city you'd like to stay in. Which city are you planning to visit?"
        elif tool_name == "suggest_activities":
            if not tool_args.get("city"):
                # Try to extract from summary before asking user
                city_from_summary = self._extract_city_from_summary(summary) if summary else None
                if city_from_summary:
                    # Auto-fill the city from summary
                    tool_args["city"] = city_from_summary
                    return None  # Validation passes now
                return "I need to know which city you'd like activities for. Which city are you visiting?"
        return None
    
    def get_tools_schema(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_flights",
                    "description": "Search for flights between cities",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "from_city": {"type": "string"},
                            "to_city": {"type": "string"},
                            "depart_date": {"type": "string"},
                            "return_date": {"type": "string"},
                            "stops": {"type": "integer"},
                            "max_price": {"type": "number"},
                            "cabin": {"type": "string"}
                        },
                        "required": ["from_city", "to_city", "depart_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_hotels",
                    "description": "Search for hotels in a city",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"},
                            "area": {"type": "string"},
                            "checkin": {"type": "string"},
                            "checkout": {"type": "string"},
                            "max_budget": {"type": "number"},
                            "rating_min": {"type": "number"}
                        },
                        "required": ["city"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "suggest_activities",
                    "description": "Suggest activities/things to do in a city",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"},
                            "interests": {"type": "array", "items": {"type": "string"}},
                            "days": {"type": "integer"},
                            "budget_tier": {"type": "string"}
                        },
                        "required": ["city"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_memory",
                    "description": "Get stored user preferences",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keys": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_memory",
                    "description": "Store or update user preferences",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"}
                        },
                        "required": ["key", "value"]
                        }
                }
            }
        ]
    
    async def process_message(self, session_id: str, message: str, 
                            client_api_key: Optional[str] = None) -> Dict[str, Any]:
        server_key = os.getenv("OPENAI_API_KEY")
        api_key = client_api_key or server_key
        
        if not api_key:
            return {
                "reply": "Please provide an OpenAI API key to use this service. You can enter it in the API key field above, or configure it on the server.",
                "actions": [],
                "memory_diff": []
            }
        
        using_client_key = bool(client_api_key)
        client = OpenAI(api_key=api_key)
        
        profile = self.memory.get_profile(session_id)
        summary = self.memory.get_conversation_summary(session_id) or ""
        last_turns = self.memory.get_last_turns(session_id)
        
        # Extract destination from summary for easier access
        summary_obj = {}
        destination_city = None
        if summary:
            try:
                summary_obj = json.loads(summary)
                destinations = summary_obj.get("destinations", [])
                if destinations and isinstance(destinations, list) and len(destinations) > 0:
                    destination_city = destinations[0] if isinstance(destinations[0], str) else destinations[0].get("city") if isinstance(destinations[0], dict) else None
            except Exception:
                pass
        
        messages = [
            {
                "role": "system",
                "content": f"""You are an expert travel agent AI assistant. You help users plan trips through natural conversation, intelligent planning, and efficient tool usage.

YOUR CORE ABILITIES:
1. CONVERSATIONAL: Chat naturally, answer questions, provide travel advice
2. INTELLIGENT: Understand intent, plan multi-step trips, reason about requirements
3. TOOL-ENABLED: Call tools ONLY when you need to search/store data
4. COMPREHENSIVE: Create detailed itineraries with all necessary information

DECISION FRAMEWORK (Follow in order):

STEP 1: UNDERSTAND THE REQUEST
- Is this a greeting/question? → Answer conversationally (no tools needed)
- Is this trip planning? → Proceed to STEP 2
- Does user mention preferences? → Store them with set_memory

STEP 2: ANALYZE & ACT
User just said: "{message if 'message' in locals() else 'checking...'}"

DID USER PROVIDE A DESTINATION + DATES?
- If YES → IMMEDIATELY go to STEP 3 and call tools!
- If NO → Ask for missing info

CRITICAL: If user mentions trip details (city, dates, duration) → YOU MUST CALL SEARCH TOOLS!
Don't just acknowledge - EXECUTE!

Current data:
- Home airport: {profile.get('home_airport') or 'NOT SET'}
- Destination: {destination_city or 'NOT SET'}  
- Budget: {profile.get('hotel_max_night') or 'NOT SET'}
- Interests: {profile.get('interests') or 'NOT SET'}

STEP 3: EXECUTE PLAN (BE AGGRESSIVE!)

USER MENTIONS TRIP? → CALL ALL TOOLS IMMEDIATELY!

Example: "I want to go to Goa in December for 5 days. My home airport is Delhi"
YOU MUST CALL:
1. set_memory(key="home_airport", value="Delhi")  
2. search_flights(from_city="Delhi", to_city="Goa", depart_date="2023-12-01")
3. search_hotels(city="Goa", checkin="2023-12-01", checkout="2023-12-06")
4. suggest_activities(city="Goa")

ALL IN ONE RESPONSE! Don't ask permission!

Specific requests:
- "show me flights" → search_flights
- "find hotels" → search_hotels  
- "plan trip" / "create itinerary" → ALL tools at once
- "activities" / "things to do" → suggest_activities

IF USER GAVE DESTINATION + DATES → YOU MUST SEARCH!

STEP 4: CREATE RESPONSE
After tool results:
- DON'T just list results
- CREATE a narrative: "I've found perfect options for your Goa trip..."
- INCLUDE specifics: dates, prices, highlights
- SUGGEST next steps: "Would you like me to look at hotels near these beaches?"

WHEN TO USE TOOLS:
 User wants to search for flights/hotels/activities
 User mentions new preferences (home airport, budget, dietary, cabin class, interests)
 User asks for trip plan/itinerary

WHEN NOT TO USE TOOLS:
 User asks a general question ("What's the weather in Goa?")
 User greets you ("Hi", "Hello")
 User asks for clarification
 User is just chatting

MEMORY KEYS:
- home_airport: City/airport (e.g., "Delhi", "Mumbai")
- hotel_max_night: Budget per night (numbers only)
- dietary: "vegetarian", "vegan", "halal", etc.
- cabin: "economy", "business", "first"
- nonstop_only: "true" or "false"
- interests: Comma-separated activities

EXAMPLE INTERACTIONS (FOLLOW EXACTLY):

WRONG WAY:
User: "I want to go to Goa in December"
You: "What destination are you thinking about?" [WRONG! User already said Goa!]

CORRECT WAY:
User: "I want to go to Goa in December for 5 days. My home airport is Delhi."
You: [IMMEDIATELY CALL: set_memory + search_flights + search_hotels + suggest_activities]
Response: "Perfect! I've found great options for your 5-day Goa trip in December from Delhi. Here are flights departing December 1st, returning December 6th..."

Just chatting (no tools):
User: "Hi"
You: "Hello! I'm your travel agent. Where would you like to go?"

User: "What's the weather in Goa?"  
You: "Goa has pleasant weather from November to February..."

Search after conversation:
User: "I like beaches"
You: [set_memory(interests="beaches")]
Response: "Noted! Beach lover!  Where would you like to go?"

User: "Goa in December"
You: [search_flights + search_hotels + suggest_activities ALL AT ONCE]
Response: "Excellent choice! Here are the best beach hotels in Goa..."

CURRENT CONTEXT:
Stored preferences: {json.dumps(profile)}
Conversation summary: {summary}
Destination: {destination_city or "Not specified yet"}
Recent conversation: {json.dumps(last_turns[-5:]) if last_turns else 'None'}

ABSOLUTE RULES (NEVER BREAK):
1. User mentions destination + dates → CALL SEARCH TOOLS IMMEDIATELY
2. Don't repeat questions - user gave info, USE IT
3. Be conversational for general questions (weather, advice, etc.)
4. Create rich narrative responses after tool results
5. If user says "plan trip to X" → CALL ALL TOOLS (flights, hotels, activities)

YOU ARE GPT-4O-MINI - YOU ARE SMART ENOUGH TO:
- Extract "Goa" from "I want to go to goa"
- Extract "December" and calculate dates
- Extract "Delhi" from "my home airport is delhi"
- THEN IMMEDIATELY SEARCH - DON'T ASK AGAIN!"""
            },
        ]
        
        # Include last N turns in the prompt for short-term context
        # This is CRITICAL - the LLM needs full conversation history to extract slots
        if last_turns:
            messages.extend(last_turns[-10:])  # Last 10 turns for context
        
        messages.extend([
            {
                "role": "user",
                "content": message
            }
        ])
        
        actions = []
        memory_diffs = []
        # Log initial memory fetch for transparency in Inspector - always show what we loaded
        initial_memory_action = Action(tool="get_memory", input={"keys": []}, output=profile)
        actions.append(initial_memory_action)
        
        max_iterations = 5
        try:
            for _ in range(max_iterations):
                try:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        tools=self.get_tools_schema(),
                        tool_choice="auto"
                    )
                except Exception as e:
                    error_msg = str(e)
                    if not using_client_key and server_key:
                        if "rate limit" in error_msg.lower() or "quota" in error_msg.lower() or "insufficient_quota" in error_msg.lower() or "invalid_api_key" in error_msg.lower():
                            return {
                                "reply": f"Server API key issue: {error_msg}. Please enter your own OpenAI API key in the field above to continue.",
                                "actions": [a.model_dump() for a in actions],
                                "memory_diff": [d.model_dump() for d in memory_diffs]
                            }
                    return {
                        "reply": f"Error calling OpenAI API: {error_msg}",
                        "actions": [a.model_dump() for a in actions],
                        "memory_diff": [d.model_dump() for d in memory_diffs]
                    }
                
                message_obj = response.choices[0].message
                messages.append(message_obj)
                
                if not message_obj.tool_calls:
                    break
                
                # PARALLEL TOOL EXECUTION - Execute all tools concurrently!
                async def execute_single_tool(tool_call):
                    """Execute a single tool call and return result with tool_call_id"""
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    # Improve date parsing for flights
                    if tool_name == "search_flights" and tool_args.get("depart_date"):
                        parsed_date = parse_date_flexible(tool_args["depart_date"])
                        if parsed_date:
                            tool_args["depart_date"] = parsed_date
                    
                    # Slot validation
                    validation_error = self._validate_slots(tool_name, tool_args, profile, summary)
                    if validation_error:
                        return {
                            "tool_call_id": tool_call.id,
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "action": Action(tool=tool_name, input=tool_args, error=validation_error),
                            "result": {"error": validation_error}
                        }
                    
                    # Create action object for this tool call
                    action = Action(tool=tool_name, input=tool_args)
                    
                    try:
                        if tool_name in ["search_flights", "search_hotels", "suggest_activities"]:
                            @retry(
                                stop=stop_after_attempt(3),
                                wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0),
                                retry=retry_if_exception_type((Exception,)),
                                reraise=True
                            )
                            async def call_tool():
                                if tool_name == "search_flights":
                                    if asyncio.iscoroutinefunction(search_flights):
                                        return await asyncio.wait_for(search_flights(**tool_args), timeout=5.0)
                                    else:
                                        return await asyncio.wait_for(
                                            asyncio.to_thread(search_flights, **tool_args), timeout=5.0
                                        )
                                elif tool_name == "search_hotels":
                                    if asyncio.iscoroutinefunction(search_hotels):
                                        return await asyncio.wait_for(search_hotels(**tool_args), timeout=5.0)
                                    else:
                                        return await asyncio.wait_for(
                                            asyncio.to_thread(search_hotels, **tool_args), timeout=5.0
                                        )
                                elif tool_name == "suggest_activities":
                                    if asyncio.iscoroutinefunction(suggest_activities):
                                        return await asyncio.wait_for(suggest_activities(**tool_args), timeout=5.0)
                                    else:
                                        return await asyncio.wait_for(
                                            asyncio.to_thread(suggest_activities, **tool_args), timeout=5.0
                                        )
                            
                            result = await call_tool()
                            action.output = result
                        elif tool_name == "get_memory":
                            keys = tool_args.get("keys", [])
                            if keys:
                                result = {k: profile.get(k) for k in keys}
                            else:
                                result = profile
                            action.output = result
                        elif tool_name == "set_memory":
                            key = tool_args["key"]
                            value = tool_args["value"]
                            
                            if key == "dietary":
                                updates = {"dietary": value}
                            elif key == "hotel_max_night" or key == "budget":
                                try:
                                    budget_val = float(value.replace(",", "").replace("lakh", "").strip())
                                    if "lakh" in value.lower():
                                        budget_val = budget_val * 100000
                                    updates = {"hotel_max_night": budget_val}
                                except:
                                    updates = {}
                            elif key == "interests":
                                if isinstance(value, str):
                                    if value.startswith("[") and value.endswith("]"):
                                        try:
                                            interests_list = ast.literal_eval(value)
                                            updates = {"interests": interests_list if isinstance(interests_list, list) else [value]}
                                        except:
                                            updates = {"interests": [v.strip() for v in value.split(",")]}
                                    else:
                                        updates = {"interests": [v.strip() for v in value.split(",")]}
                                else:
                                    updates = {"interests": value if isinstance(value, list) else [value]}
                            elif key == "nonstop_only":
                                updates = {"nonstop_only": value.lower() in ["true", "yes", "1"]}
                            elif key == "cabin":
                                updates = {"cabin": value}
                            else:
                                updates = {key: value}
                            
                            if updates:
                                diffs = self.memory.update_profile(session_id, updates)
                                for diff in diffs:
                                    memory_diffs.append(MemoryDiff(**diff))
                                result = {"updated": key, "diffs": diffs}
                            else:
                                result = {"error": "Invalid value format"}
                            action.output = result
                        else:
                            result = {"error": "Unknown tool"}
                            action.output = result
                        
                        return {
                            "tool_call_id": tool_call.id,
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "action": action,
                            "result": result
                        }
                    except Exception as e:
                        action.error = str(e)
                        return {
                            "tool_call_id": tool_call.id,
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "action": action,
                            "result": {"error": str(e)}
                        }
                
                # Execute ALL tools in parallel using asyncio.gather
                tool_results = await asyncio.gather(*[execute_single_tool(tc) for tc in message_obj.tool_calls])
                
                # Process results in order (matching original tool_call order)
                for result_data in tool_results:
                    actions.append(result_data["action"])
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result_data["tool_call_id"],
                        "content": json.dumps(result_data["result"])
                    })
        except Exception as e:
            return {
                "reply": f"Error processing request: {str(e)}",
                "actions": [a.model_dump() for a in actions],
                "memory_diff": [d.model_dump() for d in memory_diffs]
            }
        
        try:
            final_response = client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            reply = final_response.choices[0].message.content
        except Exception as e:
            error_msg = str(e)
            if not using_client_key and server_key:
                if "rate limit" in error_msg.lower() or "quota" in error_msg.lower() or "insufficient_quota" in error_msg.lower() or "invalid_api_key" in error_msg.lower():
                    reply = f"Server API key issue: {error_msg}. Please enter your own OpenAI API key in the field above to continue."
                else:
                    reply = f"Error generating response: {error_msg}"
            else:
                reply = f"Error generating response: {error_msg}"
        
        # Update conversation summary and last turns
        try:
            updated_last_turns = (last_turns or []) + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": reply or ""}
            ]
            summarizer_msgs = self._build_summarizer_prompt(summary or "{}", updated_last_turns[-10:], message, reply or "", actions)
            sum_resp = client.chat.completions.create(model=self.model, messages=summarizer_msgs)
            summary_text = sum_resp.choices[0].message.content or "{}"
            summary_json = self._safe_json(summary_text, summary or "{}")
            self.memory.update_conversation_summary(session_id, summary_json, updated_last_turns)
        except Exception:
            # If summarization fails, at least persist the last turns
            try:
                updated_last_turns = (last_turns or []) + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": reply or ""}
                ]
                self.memory.update_conversation_summary(session_id, summary or "{}", updated_last_turns)
            except Exception:
                pass
        
        # Ensure actions are always serialized properly
        serialized_actions = [a.model_dump() if hasattr(a, 'model_dump') else a for a in actions]
        serialized_memory_diff = [d.model_dump() if hasattr(d, 'model_dump') else d for d in memory_diffs]
        
        return {
            "reply": reply,
            "actions": serialized_actions,
            "memory_diff": serialized_memory_diff
        }

