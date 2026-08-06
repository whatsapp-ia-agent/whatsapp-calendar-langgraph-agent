from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph, END

class AgentState(BaseModel):
    messages: List[Dict[str, Any]]
    chat_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    next_step: Literal["classify", "catalog", "schedule", "respond"] = "classify"
    # Datos adicionales para contexto
    context: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True
