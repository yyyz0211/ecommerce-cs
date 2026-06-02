"""对话服务：会话管理、消息记录、Agent 编排"""

from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import agent_graph, _db_context
from app.agent.state import AgentState
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
    """往会话中添加一条消息"""
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
    """获取会话消息记录（按时间正序）。

    limit=None → 全量读取（摘要压缩用）
    limit=N    → 只取最近 N 条（LLM 上下文用）
    """
    await get_conversation(db, conversation_id, user_id)

    if limit:
        sub = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .subquery()
        )
        result = await db.execute(
            select(Message)
            .where(Message.id.in_(select(sub.c.id)))
            .order_by(Message.created_at.asc())
        )
    else:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
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

    流程：
    1. 加载历史消息（最多 20 条）
    2. 构建 AgentState → 运行 LangGraph
    3. 保存用户消息 + Agent 回复到数据库
    4. 返回 Agent 的文本回复
    """
    # 1. 保存用户消息
    await add_message(db, conversation, "user", user_content)

    # 2. 加载历史消息（最近 20 条），转为 LangChain 格式
    history = await get_conversation_messages(db, conversation.id, user.id, limit=20)
    lc_messages = []
    for msg in history:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "agent":
            lc_messages.append(AIMessage(content=msg.content))
        elif msg.role == "system":
            # system 消息（如摘要）作为 HumanMessage 注入，让 LLM 当成上下文理解
            lc_messages.append(HumanMessage(content=f"[历史摘要] {msg.content}"))

    # 3. 跑 Agent（db 通过 state 注入给工具节点使用）
    initial_state: AgentState = {
        "messages": lc_messages,
        "user_id": user.id,
        "conversation_id": conversation.id,
    }

    # 通过 ContextVar 将 db session 注入 Graph 节点
    _db_context.set(db)
    result = await agent_graph.ainvoke(initial_state)

    # 4. 提取 Agent 最终回复（最后一条 AI 消息）
    final_messages = result["messages"]
    agent_reply = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and msg.content:
            agent_reply = msg.content
            break

    if not agent_reply:
        agent_reply = "抱歉，我暂时无法处理您的请求，请稍后再试。"

    # 5. 保存 Agent 回复
    await add_message(db, conversation, "agent", agent_reply)

    return agent_reply
