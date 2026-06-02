"""对话路由：会话管理、历史记录"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.chat import ChatHistoryResponse, ChatMessageRequest
from app.services.auth_service import get_current_user
from app.services.chat_service import create_conversation, get_conversation, get_conversation_messages, get_user_conversations, process_agent_message

router = APIRouter(prefix="/api/chat", tags=["对话"])


@router.get("/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取用户的所有对话会话列表"""
    conversations = await get_user_conversations(db, current_user.id)
    return [
        {
            "id": c.id,
            "status": c.status,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in conversations
    ]


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


@router.post("/message")
async def send_message(
    req: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发送消息并获取 Agent 回复"""
    # 获取或创建会话
    if req.conversation_id:
        conversation = await get_conversation(db, req.conversation_id, current_user.id)
    else:
        conversation = await create_conversation(db, current_user)

    reply = await process_agent_message(db, current_user, conversation, req.content)
    return {"conversation_id": conversation.id, "reply": reply}
