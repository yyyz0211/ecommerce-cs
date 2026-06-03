"""Agent graph helper tests.

These tests cover deterministic graph helpers without calling the LLM.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.core.graph import _build_task_state, _format_memory_for_prompt
from app.agent.schemas.task_state import TaskIntent, TaskStage, TaskStatus


def _state(messages):
    return {
        "messages": messages,
        "user_id": 7,
        "conversation_id": 1,
        "db": None,
        "memory": {},
        "task_state": None,
    }


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


def test_build_task_state_marks_successful_logistics_query_done():
    state = _state(
        [
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
            ToolMessage(content="订单 1 物流：运输中", tool_call_id="call_1"),
            AIMessage(content="您的订单正在运输中。"),
        ]
    )

    task_state = _build_task_state(state)

    assert task_state.stage == TaskStage.COMPLETED
    assert task_state.intent == TaskIntent.QUERY_LOGISTICS
    assert task_state.status == TaskStatus.DONE
    assert task_state.customer_id == 7


def test_build_task_state_marks_tool_error_failed():
    state = _state(
        [
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
            ToolMessage(content="错误：未找到订单 unknown", tool_call_id="call_1"),
            AIMessage(content="没有找到这个订单。"),
        ]
    )

    task_state = _build_task_state(state)

    assert task_state.stage == TaskStage.FAILED
    assert task_state.status == TaskStatus.ERROR
