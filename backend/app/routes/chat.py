from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from app.schemas import ChatRequest, ChatResponse
from app.orchestrator import Orchestrator

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    x_openai_key: Optional[str] = Header(None, alias="X-OPENAI-KEY")
):
    try:
        orchestrator = Orchestrator()
        result = await orchestrator.process_message(
            session_id=request.session_id,
            message=request.message,
            client_api_key=x_openai_key
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    """Get conversation history and user profile for a session"""
    try:
        orchestrator = Orchestrator()
        profile = orchestrator.memory.get_profile(session_id)
        summary = orchestrator.memory.get_conversation_summary(session_id)
        turns = orchestrator.memory.get_last_turns(session_id)
        
        return {
            "session_id": session_id,
            "profile": profile,
            "summary": summary,
            "turns": turns,
            "exists": bool(turns or profile or summary)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

