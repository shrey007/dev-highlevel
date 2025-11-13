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
                "content": f"""You are a proactive travel agent AI. Your job is to EXECUTE searches and show results, not just have conversations.

CRITICAL RULES - MUST FOLLOW:
1. IMMEDIATE ACTION: When user requests flights/hotels/activities, IMMEDIATELY call the appropriate tool. DO NOT ask for confirmation, DO NOT say "would you like me to...", just DO IT.
   
2. USE CONTEXT: Check conversation summary for destinations, dates, budget, interests. If user says "show hotels" or "tell me hotels" and destination exists in summary → CALL search_hotels immediately.

3. TOOL CALLING REQUIREMENTS:
   - User says "flights" or "flight search" → call search_flights (extract cities/dates from context)
   - User says "hotels" or "show hotels" or "hotel btao" → call search_hotels (use destination from summary)
   - User says "activities" or "things to do" → call suggest_activities (use destination from summary)
   - User mentions new preference → call set_memory to store it
   
4. NEVER ASK THESE QUESTIONS IF INFO EXISTS IN CONTEXT:
   ❌ "Would you like me to search for hotels?"
   ❌ "Should I show you hotel options?"
   ❌ "Do you want to proceed with..."
   ✅ Just call the tool and present results

5. EXTRACT FROM MEMORY/CONTEXT:
   - Budget from profile.hotel_max_night or conversation
   - Interests from profile.interests or conversation
   - Destination from summary.destinations
   - Dates from conversation turns or summary

6. RESPONSE PATTERN:
   - Call tool(s) → Get results → Present results conversationally
   - Example: "Here are 5 hotels in Paris within your ₹24,000/night budget: [list hotels]"
   - NOT: "I found your preferences. Would you like me to search?"

CURRENT CONTEXT:
User preferences: {json.dumps(profile)}
Conversation summary: {summary}
Destination in context: {destination_city or "None - ask user"}
Last 5 turns: {json.dumps(last_turns[-5:]) if last_turns else 'None'}

REMEMBER: Be proactive. Execute searches. Show results. Don't ask permission when you have the information."""
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
                
                for tool_call in message_obj.tool_calls:
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
                        action = Action(tool=tool_name, input=tool_args, error=validation_error)
                        actions.append(action)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"error": validation_error})
                        })
                        continue
                    
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
                        
                        # Always append action after setting output
                        actions.append(action)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        })
                    except Exception as e:
                        action.error = str(e)
                        actions.append(action)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"error": str(e)})
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

