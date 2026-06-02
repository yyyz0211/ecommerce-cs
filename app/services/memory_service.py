"""会话记忆服务：记忆读写、摘要压缩、状态提取

与 chat_service 分离，避免循环依赖。
记忆写入在后台异步执行，不影响主对话链路。

依赖方向（单向，无循环）:
  chat_service ──→ memory_service
  graph ──→ memory_service (懒加载)
  memory_service ──→ (不依赖 chat_service 或 graph)
"""

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.errors import CONVERSATION_NOT_FOUND
from app.models.conversation import Conversation, ConversationMemory, Message


# ── 记忆读写 ──

async def get_conversation_memory(
    db: AsyncSession, conversation_id: int, user_id: int
) -> list[ConversationMemory]:
    """获取会话的所有记忆条目（summary / task_state / preference / fact）

    内联了归属校验（不调用 chat_service.get_conversation），
    避免 memory_service → chat_service 的循环依赖。
    """
    # 校验会话归属（与 chat_service.get_conversation 等价，但内联以解耦）
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
    # 校验会话归属
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise CONVERSATION_NOT_FOUND

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


# ── 后台记忆更新入口 ──

async def save_memory_background(conversation_id: int, user_id: int):
    """后台异步任务：生成并持久化会话记忆。

    由 chat_service.process_agent_message 通过 asyncio.create_task 触发，
    使用独立的 db session（AsyncSessionLocal），与主请求生命周期完全解耦。

    设计要点:
    - 用户回复已返回，此任务不阻塞主链路
    - 失败静默丢弃，不影响用户体验
    - summary 用 LLM 增量压缩，task_state 用纯规则提取
    """
    try:
        # 独立 session：主请求的 db session 在 response 返回后就关闭了
        async with AsyncSessionLocal() as db:
            messages = await _load_recent_messages(db, conversation_id, user_id)
            if not messages:
                return

            # ─── 1. 生成 summary：LLM 增量压缩 ───
            old_summary = await _load_memory_content(db, conversation_id, user_id, "summary")
            new_summary = await _summarize_memory(old_summary, messages)
            if new_summary:
                await save_conversation_memory(
                    db, conversation_id, user_id, "summary", new_summary,
                )

    except Exception:
        # 后台任务失败不影响主流程，连日志都不打——避免噪音
        pass


# ── 内部辅助 ──

async def _load_recent_messages(
    db: AsyncSession, conversation_id: int, user_id: int,
) -> list[Message]:
    """加载会话全部消息，供压缩和状态提取使用。

    内联了消息查询逻辑（不调用 chat_service.get_conversation_messages），
    避免 memory_service → chat_service 的循环依赖。
    """
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return result.scalars().all()


async def _load_memory_content(
    db: AsyncSession, conversation_id: int, user_id: int, memory_type: str,
) -> str:
    """读取指定类型的记忆内容，不存在则返回空字符串"""
    result = await db.execute(
        select(ConversationMemory).where(
            ConversationMemory.conversation_id == conversation_id,
            ConversationMemory.memory_type == memory_type,
        )
    )
    memory = result.scalar_one_or_none()
    return memory.content if memory else ""


# ── 摘要压缩提示词 ──

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
    """用 LLM 将旧摘要 + 最新消息合并压缩为新摘要。

    设计要点:
    - 只取最近 10 条消息，每条截断到 200 字符 → 控制 token 消耗
    - temperature=0.3 → 保证摘要稳定可预测
    - max_tokens=200 → 强制简洁输出
    - 失败返回空字符串 → 不影响主流程，旧摘要保持不变
    """
    recent = messages[-10:]
    dialogue_lines = []
    for m in recent:
        role_label = "用户" if m.role == "user" else "客服"
        # 截断过长内容，避免摘要上下文过长
        content = m.content[:200] + "..." if len(m.content) > 200 else m.content
        dialogue_lines.append(f"{role_label}: {content}")
    dialogue_text = "\n".join(dialogue_lines)

    user_prompt = f"[旧摘要]\n{old_summary or '（暂无）'}\n\n[最新对话]\n{dialogue_text}"

    try:
        # 摘要压缩使用独立凭证，与主对话链路隔离速率配额
        # 默认复用 OPENAI_API_KEY / OPENAI_BASE_URL，可单独配以彻底分流
        client = AsyncOpenAI(
            api_key=settings.LLM_SUMMARY_API_KEY,
            base_url=settings.LLM_SUMMARY_BASE_URL,
        )
        response = await client.chat.completions.create(
            model=settings.LLM_SUMMARY_MODEL,
            messages=[
                {"role": "system", "content": _COMPRESSION_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,   # 低温度保证摘要稳定，不每次变样
            max_tokens=200,    # 限制输出长度，强制简洁
        )
        return response.choices[0].message.content.strip()
    except Exception:
        # 压缩失败返回空，save_memory_background 会跳过写入，
        # 旧摘要保持不变
        return ""



