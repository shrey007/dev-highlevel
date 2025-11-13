from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ChatRequest(BaseModel):
    session_id: str
    message: str

class Action(BaseModel):
    tool: str
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class MemoryDiff(BaseModel):
    key: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

class ChatResponse(BaseModel):
    reply: str
    actions: List[Action] = []
    memory_diff: List[MemoryDiff] = []

