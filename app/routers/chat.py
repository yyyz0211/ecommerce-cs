"""对话路由：会话管理、历史记录

Phase 3 接入 Agent 后，POST /api/chat/message 将在此处实现。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse, ChatHistoryResponse
from app.services.auth_service import get_current_user
from app.services.chat_service import (
    create_conversation,
    get_conversation,
    get_conversation_messages,
)

router = APIRouter(prefix="/api/chat", tags=["对话"])


@router.post("/session", status_code=201)
def create_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建新的对话会话"""
    conv = create_conversation(db, current_user)
    return {"conversation_id": conv.id, "status": conv.status}


@router.get("/history/{conversation_id}", response_model=list[ChatHistoryResponse])
def get_history(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取某次对话的完整消息记录"""
    messages = get_conversation_messages(db, conversation_id, current_user.id)
    return messages


# TODO(Phase 3): POST /api/chat/message — 发送消息并获取 Agent 回复
# @router.post("/message", response_model=ChatMessageResponse)
# def send_message(req: ChatMessageRequest, ...):
#     """用户发送消息，Agent 回复"""
