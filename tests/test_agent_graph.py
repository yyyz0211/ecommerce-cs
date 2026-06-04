"""Agent graph helper tests.

These tests cover deterministic graph helpers without calling the LLM.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.core.graph import _format_memory_for_prompt
from app.agent.core.state_machine import reduce_task_state
from app.agent.schemas.results import ToolResult
from app.agent.schemas.task_state import TaskIntent, TaskStage, TaskStatus


def test_format_memory_for_prompt_groups_by_type():
    prompt = _format_memory_for_prompt(
        {
            "summary": "用户正在查询订单。",
            "task_state": '{"stage":"completed","intent":"query_logistics"}',
            "preference": "用户喜欢短信通知。",
            "fact": "用户是会员。",
        }
    )

    assert "[会话摘要]" in prompt
    assert "[当前任务状态]" in prompt
    assert "[用户偏好]" in prompt
    assert "[已知事实]" in prompt
    assert '"intent": "query_logistics"' in prompt


def test_reduce_task_state_marks_successful_logistics_query_done():
    tool_result = ToolResult(
        ok=True,
        tool="query_logistics",
        message="订单 1 物流：运输中",
        data={"order_id": 1},
        task_patch={
            "stage": "completed",
            "intent": "query_logistics",
            "status": "done",
            "order_id": 1,
        },
    )
    messages = [
        HumanMessage(content="查一下物流"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "query_logistics",
                    "args": {"order_id": "202605280001"},
                }
            ],
        ),
        ToolMessage(content=tool_result.to_tool_message(), tool_call_id="call_1"),
        AIMessage(content="您的订单正在运输中。"),
    ]

    task_state = reduce_task_state(user_id=7, messages=messages)

    assert task_state.stage == TaskStage.COMPLETED
    assert task_state.intent == TaskIntent.QUERY_LOGISTICS
    assert task_state.status == TaskStatus.DONE
    assert task_state.customer_id == 7


def test_reduce_task_state_marks_tool_error_failed():
    tool_result = ToolResult(
        ok=False,
        tool="query_order_detail",
        message="错误：未找到订单 unknown",
        error_code="TOOL_ERROR",
    )
    messages = [
        HumanMessage(content="查一下订单"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "query_order_detail",
                    "args": {"order_id": "unknown"},
                }
            ],
        ),
        ToolMessage(content=tool_result.to_tool_message(), tool_call_id="call_1"),
        AIMessage(content="没有找到这个订单。"),
    ]

    task_state = reduce_task_state(user_id=7, messages=messages)

    assert task_state.stage == TaskStage.FAILED
    assert task_state.status == TaskStatus.ERROR
