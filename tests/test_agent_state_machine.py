"""Agent 状态机与结构化结果测试。"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.schemas.results import ToolResult
from app.agent.core.state_machine import reduce_task_state
from app.agent.schemas.task_state import TaskIntent, TaskStage, TaskStatus


def test_tool_result_round_trip_for_tool_message():
    result = ToolResult(
        ok=True,
        tool="query_logistics",
        message="订单 18 物流：运输中",
        data={"order_id": 18, "status": "运输中"},
        task_patch={
            "stage": "completed",
            "intent": "query_logistics",
            "status": "done",
            "order_id": 18,
        },
    )

    parsed = ToolResult.from_tool_message(result.to_tool_message())

    assert parsed.ok is True
    assert parsed.tool == "query_logistics"
    assert parsed.data["order_id"] == 18
    assert parsed.task_patch["intent"] == "query_logistics"


def test_reduce_task_state_uses_structured_tool_patch():
    tool_result = ToolResult(
        ok=True,
        tool="query_logistics",
        message="订单 18 物流：运输中",
        data={"order_id": 18},
        task_patch={
            "stage": "completed",
            "intent": "query_logistics",
            "status": "done",
            "order_id": 18,
        },
    )
    messages = [
        HumanMessage(content="查一下 18 的物流"),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "call_1", "name": "query_logistics", "args": {"order_id": "18"}},
            ],
        ),
        ToolMessage(content=tool_result.to_tool_message(), tool_call_id="call_1"),
        AIMessage(content="您的订单正在运输中。"),
    ]

    state = reduce_task_state(user_id=7, messages=messages)

    assert state.stage == TaskStage.COMPLETED
    assert state.intent == TaskIntent.QUERY_LOGISTICS
    assert state.status == TaskStatus.DONE
    assert state.order_id == 18
    assert state.customer_id == 7


def test_reduce_task_state_marks_structured_tool_error_failed():
    tool_result = ToolResult(
        ok=False,
        tool="submit_after_sale",
        message="错误：请提供售后原因",
        error_code="TOOL_INPUT_ERROR",
        task_patch={
            "stage": "failed",
            "intent": "submit_after_sale",
            "status": "error",
        },
    )

    state = reduce_task_state(user_id=7, tool_results=[tool_result])

    assert state.stage == TaskStage.FAILED
    assert state.intent == TaskIntent.SUBMIT_AFTER_SALE
    assert state.status == TaskStatus.ERROR
