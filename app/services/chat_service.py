"""对话服务：会话管理、消息记录、Agent 编排"""

import asyncio
import json
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.errors import CONVERSATION_NOT_FOUND
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.memory_service import save_conversation_memory, save_memory_background


async def get_or_create_conversation(db: AsyncSession, user: User) -> Conversation:
    """获取或创建用户的客服对话会话 -- 一个用户只有一个 active 会话"""
    # 先查是否已有 active 会话
    result = await db.execute(
        select(Conversation).where(
            Conversation.user_id == user.id,
            Conversation.status == "active",
        ).order_by(Conversation.updated_at.desc()).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # 没有则创建新的
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
    """获取会话消息记录（按时间正序）。

    limit=None → 全量读取（摘要压缩用）
    limit=N    → 只取最近 N 条（LLM 上下文用）
    """
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

    流程：
    1. 保存用户消息
    2. 加载历史消息 → 构建 AgentState（记忆由 load_memory 节点从 DB 加载）
    3. 运行 LangGraph
    4. 从图结果中提取 agent_reply + 结构化 task_state
    5. 保存 Agent 回复 + task_state 到 DB
    6. 后台异步生成 summary（LLM 压缩）
    7. 返回 Agent 回复
    """
    # 1. 保存用户消息
    await add_message(db, conversation, "user", user_content)

    # 2. 加载历史消息（最近 20 条），转为 LangChain 格式
    #    记忆不再在这里注入消息列表，而是由 graph 的 load_memory 节点加载到 state.memory
    history = await get_conversation_messages(db, conversation.id, user.id, limit=20)
    lc_messages = []
    for msg in history:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "agent":
            lc_messages.append(AIMessage(content=msg.content))

    # 3. 跑 Agent
    initial_state: AgentState = {
        "messages": lc_messages,
        "user_id": user.id,
        "conversation_id": conversation.id,
        "db": db,
        "memory": {},
    }
    result = await agent_graph.ainvoke(initial_state)

    # 4. 提取 Agent 回复 + 结构化 task_state
    #    task_state 从 AIMessage 的 tool_calls 提取，不依赖自然语言关键词匹配
    final_messages = result["messages"]
    agent_reply = ""
    tool_names: set[str] = set()
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage):
            if not agent_reply and msg.content:
                agent_reply = msg.content
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_names.add(tc["name"])

    if not agent_reply:
        agent_reply = "抱歉，我暂时无法处理您的请求，请稍后再试。"

    # 5. 保存 Agent 回复 + 结构化 task_state
    await add_message(db, conversation, "agent", agent_reply)

    if "submit_after_sale" in tool_names:
        last_action = "submitted_after_sale"
    elif tool_names:
        last_action = "queried_order"
    else:
        last_action = "chat"
    await save_conversation_memory(
        db, conversation.id, user.id, "task_state",
        json.dumps({"last_action": last_action, "tools_called": list(tool_names)}, ensure_ascii=False),
    )

    # 6. 后台异步生成 summary（LLM 压缩，不阻塞用户回复）
    asyncio.create_task(
        save_memory_background(conversation.id, user.id)
    )

    return agent_reply
