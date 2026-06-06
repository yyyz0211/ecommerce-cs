"""对话服务：会话管理、消息记录、Agent 编排"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.core.runtime import run_agent
from app.errors import CONVERSATION_NOT_FOUND
from app.logger import agent_logger
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.memory_service import save_memory_background, save_task_state, schedule_background_task

AGENT_RECENT_MESSAGE_LIMIT = 10


async def get_or_create_conversation(db: AsyncSession, user: User) -> Conversation:
    """获取或创建用户的客服对话会话 -- 一个用户只有一个 active 会话"""
    result = await db.execute(
        select(Conversation).where(
            Conversation.user_id == user.id,
            Conversation.status == "active",
        ).order_by(Conversation.updated_at.desc()).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def add_message(
    db: AsyncSession, conversation: Conversation, role: str, content: str
) -> Message:
    """往会话中添加一条消息"""
    message = Message(conversation_id=conversation.id, role=role, content=content)
    db.add(message)
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


async def get_user_conversations(db: AsyncSession, user_id: int) -> list[Conversation]:
    """获取用户的所有对话会话，按最后活动时间倒序"""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


async def get_conversation_messages(
    db: AsyncSession, conversation_id: int, user_id: int, limit: Optional[int] = None
) -> list[Message]:
    """获取会话消息记录（按时间正序）。"""
    await get_conversation(db, conversation_id, user_id)

    if limit is not None:
        subquery = (
            select(Message.id)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
            .subquery()
        )
        result = await db.execute(
            select(Message)
            .where(Message.id.in_(select(subquery.c.id)))
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
    else:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )

    return result.scalars().all()


async def process_agent_message(
    db: AsyncSession,
    user: User,
    conversation: Conversation,
    user_content: str,
) -> str:
    """
    处理用户消息并返回 Agent 回复
    """
    await add_message(db, conversation, "user", user_content)

    history = await get_conversation_messages(db, conversation.id, user.id, limit=AGENT_RECENT_MESSAGE_LIMIT)
    agent_result = await run_agent(
        db=db,
        user=user,
        conversation_id=conversation.id,
        messages=history,
    )

    await add_message(db, conversation, "agent", agent_result.reply)
    try:
        await save_task_state(db, conversation.id, user.id, agent_result.task_state)
    except Exception:
        agent_logger.exception(
            "主链路保存 task_state 失败，将交由后台任务兜底: conversation_id=%s user_id=%s",
            conversation.id,
            user.id,
        )

    schedule_background_task(
        save_memory_background(
            conversation.id,
            user.id,
            task_state=agent_result.task_state,
        ),
        name=f"save_memory:{conversation.id}:{user.id}",
    )

    return agent_result.reply
