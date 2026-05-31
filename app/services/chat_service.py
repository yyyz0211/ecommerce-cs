"""对话服务：会话管理、消息记录"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import CONVERSATION_NOT_FOUND
from app.models.conversation import Conversation, Message
from app.models.user import User


async def create_conversation(db: AsyncSession, user: User) -> Conversation:
    """为用户创建一个新的客服对话会话"""
    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def add_message(
    db: AsyncSession, conversation: Conversation, role: str, content: str
) -> Message:
    """往会话中添加一条消息，同时刷新会话的 updated_at"""
    message = Message(conversation_id=conversation.id, role=role, content=content)
    db.add(message)
    conversation.status = conversation.status
    await db.commit()
    await db.refresh(message)
    return message


async def get_conversation(
    db: AsyncSession, conversation_id: int, user_id: int
) -> Conversation:
    """获取会话，校验归属"""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise CONVERSATION_NOT_FOUND
    return conversation


async def get_conversation_messages(
    db: AsyncSession, conversation_id: int, user_id: int
) -> list[Message]:
    """获取会话的所有消息记录（按时间正序），先校验会话归属"""
    await get_conversation(db, conversation_id, user_id)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return result.scalars().all()
