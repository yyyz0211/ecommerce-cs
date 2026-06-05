"""会话记忆服务：记忆读写、摘要压缩、状态提取

与 chat_service 分离，避免循环依赖。
记忆写入在后台异步执行，不影响主对话链路。

依赖方向（单向，无循环）:
  chat_service ──→ memory_service
  graph ──→ memory_service (懒加载)
  memory_service ──→ (不依赖 chat_service 或 graph)
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas.task_state import MemoryType, TaskState
from app.config import settings
from app.database import AsyncSessionLocal
from app.errors import CONVERSATION_NOT_FOUND
from app.logger import agent_logger
from app.models.conversation import Conversation, ConversationMemory, Message


# ── 记忆读写 ──

async def get_conversation_memory(
    db: AsyncSession, conversation_id: int, user_id: int
) -> list[ConversationMemory]:
    """获取会话的所有记忆条目（summary / task_state / preference / fact）

    内联了归属校验（不调用 chat_service.get_conversation），
    避免 memory_service → chat_service 的循环依赖。
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise CONVERSATION_NOT_FOUND

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
    """保存或更新单条会话记忆。

    同一 memory_type 只保留最新一条（覆盖写），不累积历史版本。
    归属校验内联以避免循环依赖，与 get_conversation_memory 同理。
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise CONVERSATION_NOT_FOUND

    try:
        memory = await _upsert_conversation_memory(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id,
            memory_type=memory_type,
            content=content,
        )
        await db.commit()
        return memory
    except IntegrityError:
        await db.rollback()
        agent_logger.exception(
            "保存会话记忆冲突: conversation_id=%s memory_type=%s",
            conversation_id,
            memory_type,
        )
        raise


async def _upsert_conversation_memory(
    *,
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
    memory_type: str,
    content: str,
) -> ConversationMemory:
    values = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "memory_type": memory_type,
        "content": content,
    }

    stmt = mysql_insert(ConversationMemory).values(**values)
    stmt = stmt.on_duplicate_key_update(
        content=content,
        user_id=user_id,
        updated_at=func.now(),
    )
    await db.execute(stmt)

    result = await db.execute(
        select(ConversationMemory).where(
            ConversationMemory.conversation_id == conversation_id,
            ConversationMemory.memory_type == memory_type,
        )
    )
    return result.scalar_one()


async def save_task_state(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
    state: TaskState,
) -> ConversationMemory:
    """把结构化 task_state 序列化为 JSON 后落库。

    这里保留单独入口，是为了让 chat_service 只关心“保存状态”，
    不需要知道 JSON 序列化细节。"""
    return await save_conversation_memory(
        db,
        conversation_id,
        user_id,
        "task_state",
        state.model_dump_json(),
    )


def parse_task_state(content: str) -> TaskState:
    """把数据库里的 task_state JSON 反序列化回强类型对象。"""
    data = json.loads(content)
    return TaskState.model_validate(data)


# ── 后台记忆更新入口 ──

async def save_memory_background(
    conversation_id: int,
    user_id: int,
    task_state: Optional[TaskState] = None,
):
    """后台异步任务：生成并持久化会话记忆。

    由 chat_service.process_agent_message 通过 schedule_background_task 触发，
    使用独立的 db session（AsyncSessionLocal），与主请求生命周期完全解耦。

    设计要点:
    - 用户回复已返回，此任务不阻塞主链路
    - 失败会记录日志，方便排查 summary / task_state 的落库问题
    - summary 用 LLM 增量压缩，task_state 作为兜底持久化保障
    """
    try:
        async with AsyncSessionLocal() as db:
            if task_state is not None:
                try:
                    await save_task_state(db, conversation_id, user_id, task_state)
                except Exception:
                    agent_logger.exception(
                        "后台保存 task_state 失败: conversation_id=%s user_id=%s",
                        conversation_id,
                        user_id,
                    )

            rule_cursor = await _load_memory_content(
                db, conversation_id, user_id, MemoryType.RULE_CURSOR.value
            )
            await _extract_rule_memories(
                db, conversation_id, user_id, after_id=_parse_cursor(rule_cursor)
            )

            cursor = await _load_memory_content(
                db, conversation_id, user_id, MemoryType.SUMMARY_CURSOR.value
            )
            messages = await _load_recent_messages(db, conversation_id, user_id, after_id=_parse_cursor(cursor))
            if not messages:
                return

            old_summary = await _load_memory_content(db, conversation_id, user_id, MemoryType.SUMMARY.value)
            new_summary = await _summarize_memory(old_summary, messages)
            if new_summary:
                await save_conversation_memory(
                    db, conversation_id, user_id, MemoryType.SUMMARY.value, new_summary,
                )
                await save_conversation_memory(
                    db,
                    conversation_id,
                    user_id,
                    MemoryType.SUMMARY_CURSOR.value,
                    str(messages[-1].id),
                )

    except Exception:
        agent_logger.exception(
            "后台保存会话记忆失败: conversation_id=%s user_id=%s",
            conversation_id,
            user_id,
        )


# ── 内部辅助 ──

async def _load_recent_messages(
    db: AsyncSession, conversation_id: int, user_id: int, after_id: Optional[int] = None,
) -> list[Message]:
    """加载待压缩消息，按时间正序返回。

    首次压缩没有 cursor 时取最近 10 条；已有 cursor 时读取 cursor 后的
    全部新增消息，并按 id 正序交给摘要模型，保证增量摘要不跳过中间消息。
    """
    filters = [
        Message.conversation_id == conversation_id,
        Conversation.user_id == user_id,
    ]
    if after_id is not None:
        result = await db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(*filters, Message.id > after_id)
            .order_by(Message.id.asc())
        )
        return result.scalars().all()

    recent_ids = (
        select(Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(*filters)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(10)
        .subquery()
    )
    result = await db.execute(
        select(Message)
        .where(Message.id.in_(select(recent_ids.c.id)))
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return result.scalars().all()


def _parse_cursor(value: str) -> Optional[int]:
    try:
        cursor = int(value)
    except (TypeError, ValueError):
        return None
    return cursor if cursor > 0 else None


async def _load_memory_content(
    db: AsyncSession, conversation_id: int, user_id: int, memory_type: str,
) -> str:
    """读取指定类型的记忆内容，不存在则返回空字符串。"""
    result = await db.execute(
        select(ConversationMemory)
        .join(Conversation, ConversationMemory.conversation_id == Conversation.id)
        .where(
            ConversationMemory.conversation_id == conversation_id,
            ConversationMemory.memory_type == memory_type,
            Conversation.user_id == user_id,
        )
    )
    memory = result.scalar_one_or_none()
    return memory.content if memory else ""


async def _extract_rule_memories(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
    after_id: Optional[int] = None,
) -> None:
    messages = await _load_recent_messages(db, conversation_id, user_id, after_id=after_id)
    if not messages:
        return

    preference = _extract_preference(messages)
    if preference:
        await save_conversation_memory(
            db, conversation_id, user_id, MemoryType.PREFERENCE.value, preference
        )

    fact = _extract_fact(messages)
    if fact:
        await save_conversation_memory(
            db, conversation_id, user_id, MemoryType.FACT.value, fact
        )

    await save_conversation_memory(
        db,
        conversation_id,
        user_id,
        MemoryType.RULE_CURSOR.value,
        str(messages[-1].id),
    )


def _extract_preference(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role != "user":
            continue
        content = message.content or ""
        if any(keyword in content for keyword in ("简洁", "简短", "短一点", "少一点")):
            return "用户希望回答简洁。"
        if any(keyword in content for keyword in ("详细", "展开说", "多解释")):
            return "用户希望回答更详细。"
    return ""


def _extract_fact(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role != "user":
            continue
        content = message.content or ""
        address_match = re.search(r"(?:默认地址|收货地址)(?:是|在|：|:)\s*([^。！？\\n]+)", content)
        if address_match:
            return f"用户的默认地址是{address_match.group(1).strip()}。"
    return ""


def schedule_background_task(coro, *, name: str) -> asyncio.Task:
    started = asyncio.get_running_loop().time()
    task = asyncio.create_task(coro, name=name)

    def _log_result(done: asyncio.Task) -> None:
        elapsed = asyncio.get_running_loop().time() - started
        try:
            done.result()
        except asyncio.CancelledError:
            agent_logger.warning("后台任务被取消: name=%s elapsed=%.3fs", name, elapsed)
        except Exception:
            agent_logger.exception("后台任务失败: name=%s elapsed=%.3fs", name, elapsed)
        else:
            agent_logger.info("后台任务完成: name=%s elapsed=%.3fs", name, elapsed)

    task.add_done_callback(_log_result)
    return task


_COMPRESSION_PROMPT = """你是会话摘要生成器。你的任务是将旧摘要与新对话合并，输出一份简洁的压缩摘要。

## 摘要应包含
- 用户当前在做什么（主题）
- 用户想达成什么（目标）
- 推进到哪一步了（进展）
- 下一步需要做什么（意图）

## 摘要长度
2-4 句话，用中文。极简，只保留对后续对话有用的信息。

## 不要包含
- 订单号、物流单号等数字 ID
- 工具返回的原始数据
- 对话流水帐
- 未确认的推测

## 输出格式
直接输出摘要文本，不要加任何前缀、标签或解释。"""


async def _summarize_memory(
    old_summary: str, messages: list[Message],
) -> str:
    """把旧摘要与最近对话合并成新摘要。

    `messages` 由 `_load_recent_messages` 控制数量，避免 prompt 无限增长。"""
    lines = []
    for m in messages:
        role = "用户" if m.role == "user" else "客服"
        lines.append(f"{role}: {m.content}")
    new_dialogue = "\n".join(lines)

    client = AsyncOpenAI(api_key=settings.LLM_SUMMARY_API_KEY, base_url=settings.LLM_SUMMARY_BASE_URL)
    resp = await client.chat.completions.create(
        model=settings.LLM_SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": _COMPRESSION_PROMPT},
            {
                "role": "user",
                "content": f"旧摘要：\n{old_summary or '（无）'}\n\n新对话：\n{new_dialogue}",
            },
        ],
    )
    return (resp.choices[0].message.content or "").strip()
