"""Agent 任务状态机。

这里把“怎么从当前轮上下文得到 task_state”的逻辑从 graph 中拆出来，
让 graph 专注编排，让状态规则可以被单独测试和迭代。

说明：当前 `TaskState.confidence` 字段承载的是启发式分数，
由规则和上下文信号加权得到，不是校准后的真实概率。
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from typing import Optional

from app.agent.core.confidence import calculate_heuristic_score
from app.agent.schemas.results import ToolResult, parse_tool_results_from_messages
from app.agent.schemas.task_state import (
    NextAction,
    TaskIntent,
    TaskStage,
    TaskState,
    TaskStatus,
)


_TOOL_INTENT_MAP = {
    "query_orders": TaskIntent.QUERY_ORDER_STATUS,
    "query_order_detail": TaskIntent.QUERY_ORDER_STATUS,
    "query_logistics": TaskIntent.QUERY_LOGISTICS,
    "submit_after_sale": TaskIntent.SUBMIT_AFTER_SALE,
}


def reduce_task_state(
    *,
    user_id: int,
    old_state: Optional[TaskState] = None,
    messages: Optional[list] = None,
    tool_results: Optional[list[ToolResult]] = None,
) -> TaskState:
    """根据旧状态、当前消息和工具结果生成新任务状态。"""
    messages = messages or []
    tool_results = tool_results if tool_results is not None else parse_tool_results_from_messages(messages)

    last_user_message = _last_user_message(messages)
    tool_names = _tool_names(messages)
    latest_tool = tool_results[-1] if tool_results else None

    if latest_tool and latest_tool.task_patch:
        return _state_from_patch(user_id, old_state, latest_tool)

    if latest_tool and not latest_tool.ok:
        return TaskState(
            stage=TaskStage.FAILED,
            intent=_intent_from_tool(latest_tool.tool) or _intent_from_old(old_state),
            status=TaskStatus.ERROR,
            order_id=_order_id_from_tool(latest_tool) or (old_state.order_id if old_state else None),
            customer_id=user_id,
            heuristic_score=_heuristic_score(has_tool=True, has_user=bool(last_user_message), error=True),
            next_action=NextAction.REPLY_USER,
        )

    if latest_tool:
        return TaskState(
            stage=TaskStage.COMPLETED,
            intent=_intent_from_tool(latest_tool.tool) or _intent_from_old(old_state),
            status=TaskStatus.DONE,
            order_id=_order_id_from_tool(latest_tool) or (old_state.order_id if old_state else None),
            customer_id=user_id,
            confidence=_heuristic_score(has_tool=True, has_user=bool(last_user_message)),
            next_action=NextAction.REPLY_USER,
        )

    if tool_names:
        # 兼容旧测试或异常路径：有工具调用但没有结构化结果。
        return TaskState(
            stage=TaskStage.PROCESSING,
            intent=_intent_from_tool(tool_names[-1]) or _intent_from_old(old_state),
            status=TaskStatus.IN_PROGRESS,
            order_id=old_state.order_id if old_state else None,
            customer_id=user_id,
            confidence=_heuristic_score(has_tool=True, has_user=bool(last_user_message)),
            next_action=NextAction.CALL_BACKEND_API,
        )

    if "订单" in last_user_message or "物流" in last_user_message:
        intent = TaskIntent.QUERY_LOGISTICS if "物流" in last_user_message else TaskIntent.QUERY_ORDER_STATUS
        return TaskState(
            stage=TaskStage.AWAITING_ORDER_ID,
            intent=intent,
            status=TaskStatus.PENDING,
            order_id=old_state.order_id if old_state else None,
            customer_id=user_id,
            heuristic_score=_heuristic_score(has_tool=False, has_user=True),
            next_action=NextAction.ASK_USER_FOR_ORDER_ID,
        )

    return TaskState(
        stage=TaskStage.NEW,
        intent=TaskIntent.OTHER,
        status=TaskStatus.PENDING,
        order_id=old_state.order_id if old_state else None,
        customer_id=user_id,
        heuristic_score=_heuristic_score(has_tool=False, has_user=bool(last_user_message)),
        next_action=NextAction.REPLY_USER,
    )


def _state_from_patch(user_id: int, old_state: Optional[TaskState], tool_result: ToolResult) -> TaskState:
    patch = dict(tool_result.task_patch or {})
    order_id = patch.pop("order_id", None) or _order_id_from_tool(tool_result)
    heuristic_score = patch.pop("confidence", None)
    if heuristic_score is None:
        heuristic_score = _heuristic_score(has_tool=True, has_user=True, error=not tool_result.ok)

    base = {
        "stage": TaskStage.COMPLETED if tool_result.ok else TaskStage.FAILED,
        "intent": _intent_from_tool(tool_result.tool) or _intent_from_old(old_state),
        "status": TaskStatus.DONE if tool_result.ok else TaskStatus.ERROR,
        "order_id": order_id or (old_state.order_id if old_state else None),
        "customer_id": user_id,
        "confidence": heuristic_score,
        "next_action": NextAction.REPLY_USER,
    }
    base.update(patch)
    return TaskState(**base)


def _last_user_message(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content or ""
    return ""


def _tool_names(messages: list) -> list[str]:
    names = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            names.extend(tc["name"] for tc in msg.tool_calls)
    return names


def _intent_from_tool(tool_name: Optional[str]) -> Optional[TaskIntent]:
    return _TOOL_INTENT_MAP.get(tool_name or "")


def _intent_from_old(old_state: Optional[TaskState]) -> TaskIntent:
    return old_state.intent if old_state else TaskIntent.OTHER


def _order_id_from_tool(tool_result: ToolResult) -> Optional[int]:
    if tool_result.data and isinstance(tool_result.data.get("order_id"), int):
        return tool_result.data["order_id"]
    if tool_result.task_patch and isinstance(tool_result.task_patch.get("order_id"), int):
        return tool_result.task_patch["order_id"]
    return None


def _heuristic_score(*, has_tool: bool, has_user: bool, error: bool = False) -> float:
    return calculate_heuristic_score(
        model_signal=0.4 if error else 0.5,
        rule_signal=0.7 if has_tool else 0.3,
        context_signal=0.8 if has_user else 0.2,
    )
