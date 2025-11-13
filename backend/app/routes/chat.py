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

