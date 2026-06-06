"""Agent Runtime。

对 service 层隐藏 LangGraph message/state 细节，稳定返回 AgentResult。
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.core.graph import get_agent_graph
from app.agent.schemas.results import AgentResult, parse_tool_calls_from_messages
from app.agent.schemas.state import AgentState
from app.agent.schemas.task_state import NextAction, TaskIntent, TaskStage, TaskState, TaskStatus
from app.models.conversation import Message
from app.models.user import User


def messages_to_langchain(messages: list[Message]) -> list:
    """把数据库消息转换成 LangChain 消息。"""
    lc_messages = []
    for msg in messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "agent":
            lc_messages.append(AIMessage(content=msg.content))
    return lc_messages


async def run_agent(
    *,
    db: AsyncSession,
    user: User,
    conversation_id: int,
    messages: list[Message],
) -> AgentResult:
    """运行 Agent 图，并返回 service 层可直接消费的结构化结果。"""
    initial_state: AgentState = {
        "messages": messages_to_langchain(messages),
        "user_id": user.id,
        "conversation_id": conversation_id,
        "db": db,
        "memory": {},
        "task_state": None,
        "tool_iterations": 0,
    }
    result = await get_agent_graph().ainvoke(initial_state)
    final_messages = result["messages"]
    task_state = _coerce_task_state(result.get("task_state"), user.id)
    tool_calls = parse_tool_calls_from_messages(final_messages)

    return AgentResult(
        reply=_extract_agent_reply(final_messages),
        task_state=task_state,
        tool_calls=tool_calls,
        tool_call_count=len(tool_calls),
        confidence=task_state.confidence,
        should_transfer=task_state.intent == TaskIntent.TRANSFER_HUMAN,
    )


def _extract_agent_reply(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "抱歉，我暂时无法处理您的请求，请稍后再试。"


def _coerce_task_state(value, user_id: int) -> TaskState:
    if isinstance(value, TaskState):
        return value
    if isinstance(value, dict):
        return TaskState.model_validate(value)
    return TaskState(
        stage=TaskStage.NEW,
        intent=TaskIntent.OTHER,
        status=TaskStatus.PENDING,
        customer_id=user_id,
        confidence=0.5,
        next_action=NextAction.REPLY_USER,
    )
