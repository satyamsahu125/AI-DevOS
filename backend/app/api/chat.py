from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..agents.chat_router import ChatResponse, ChatRouter
from .dependencies import get_chat_router

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    context: str | None = None


@router.post("/projects/{project_id}/chat", response_model=ChatResponse)
def project_chat(
    project_id: str,
    request: ChatRequest,
    chat_router: ChatRouter = Depends(get_chat_router),
) -> ChatResponse:
    return chat_router.handle(project_id=project_id, message=request.message)
