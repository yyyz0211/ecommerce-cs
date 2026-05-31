"""对话路由：会话管理、历史记录"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.chat import ChatHistoryResponse
from app.services.auth_service import get_current_user
from app.services.chat_service import create_conversation, get_conversation_messages

router = APIRouter(prefix="/api/chat", tags=["对话"])


@router.post("/session", status_code=201)
async def create_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新的对话会话"""
    conv = await create_conversation(db, current_user)
    return {"conversation_id": conv.id, "status": conv.status}


@router.get("/history/{conversation_id}", response_model=list[ChatHistoryResponse])
async def get_history(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取某次对话的完整消息记录"""
    return await get_conversation_messages(db, conversation_id, current_user.id)


# TODO(Phase 3): POST /api/chat/message — 发送消息并获取 Agent 回复
