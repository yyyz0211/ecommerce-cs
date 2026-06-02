"""对话服务：会话管理、消息记录、Agent 编排"""

from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import _db_context, agent_graph
from app.agent.state import AgentState
from app.errors import CONVERSATION_NOT_FOUND
from app.models.conversation import Conversation, ConversationMemory, Message
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


async def get_conversation_memory(
    db: AsyncSession, conversation_id: int, user_id: int
) -> list[ConversationMemory]:
    """获取会话的记忆摘要/偏好/事实等"""
    await get_conversation(db, conversation_id, user_id)
    result = await db.execute(
        select(ConversationMemory)
        .where(ConversationMemory.conversation_id == conversation_id)
        .order_by(ConversationMemory.updated_at.desc(), ConversationMemory.id.desc())
    )
    return result.scalars().all()


async def save_conversation_memory(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
    memory_type: str,
    content: str,
) -> ConversationMemory:
    """保存或更新会话记忆"""
    await get_conversation(db, conversation_id, user_id)

    result = await db.execute(
        select(ConversationMemory).where(
            ConversationMemory.conversation_id == conversation_id,
            ConversationMemory.memory_type == memory_type,
        )
    )
    memory = result.scalar_one_or_none()

    if memory:
        memory.content = content
    else:
        memory = ConversationMemory(
            conversation_id=conversation_id,
            user_id=user_id,
            memory_type=memory_type,
            content=content,
        )
        db.add(memory)

    await db.commit()
    await db.refresh(memory)
    return memory


async def process_agent_message(
    db: AsyncSession,
    user: User,
    conversation: Conversation,
    user_content: str,
) -> str:
    """
    处理用户消息并返回 Agent 回复

    流程：
    1. 加载历史记忆与历史消息
    2. 构建 AgentState → 运行 LangGraph
    3. 保存用户消息 + Agent 回复到数据库
    4. 返回 Agent 的文本回复
    """
    # 1. 保存用户消息
    await add_message(db, conversation, "user", user_content)

    # 2. 加载会话记忆（单独表）
    memories = await get_conversation_memory(db, conversation.id, user.id)
    memory_text = "\n".join(
        f"- {memory.memory_type}: {memory.content}" for memory in memories if memory.content
    )

    # 3. 加载历史消息（最近 20 条），转为 LangChain 格式
    history = await get_conversation_messages(db, conversation.id, user.id, limit=20)
    lc_messages = []
    for msg in history:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "agent":
            lc_messages.append(AIMessage(content=msg.content))

    if memory_text:
        lc_messages.insert(
            0,
            HumanMessage(
                content=f"[会话记忆]\n{memory_text}\n\n请结合以上记忆理解当前对话，但不要把它当成用户新发言。"
            ),
        )

    # 4. 跑 Agent（db 通过 state 注入给工具节点使用）
    initial_state: AgentState = {
        "messages": lc_messages,
        "user_id": user.id,
        "conversation_id": conversation.id,
    }

    # 通过 ContextVar 将 db session 注入 Graph 节点
    _db_context.set(db)
    result = await agent_graph.ainvoke(initial_state)

    # 5. 提取 Agent 最终回复（最后一条 AI 消息）
    final_messages = result["messages"]
    agent_reply = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and msg.content:
            agent_reply = msg.content
            break

    if not agent_reply:
        agent_reply = "抱歉，我暂时无法处理您的请求，请稍后再试。"

    # 6. 保存 Agent 回复
    await add_message(db, conversation, "agent", agent_reply)

    return agent_reply
