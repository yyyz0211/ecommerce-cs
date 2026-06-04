"""Agent runtime 的结构化结果模型。"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, Field

from app.agent.schemas.task_state import TaskState


class ToolResult(BaseModel):
    """工具执行后的稳定返回格式。

    message 面向 LLM，可直接作为 ToolMessage 内容的一部分；
    data / task_patch 面向后端，用于状态机和后续调试。
    """

    ok: bool
    tool: str
    message: str
    data: Optional[dict[str, Any]] = None
    task_patch: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None

    def to_tool_message(self) -> str:
        """序列化为 ToolMessage 内容，保留结构化信息给后续节点解析。"""
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_tool_message(cls, content: str) -> "ToolResult":
        """从 ToolMessage 内容恢复 ToolResult。

        兼容旧的纯文本工具结果，方便渐进迁移和测试。
        """
        try:
            return cls.model_validate_json(content)
        except Exception:
            ok = not content.startswith("错误")
            return cls(
                ok=ok,
                tool="unknown",
                message=content,
                error_code=None if ok else "TOOL_ERROR",
            )

    def message_for_log(self, max_len: int = 120) -> str:
        text = self.message
        return text[:max_len] + "..." if len(text) > max_len else text


class ToolCallRecord(BaseModel):
    """一次工具调用记录，供 AgentResult 返回给 service 层。"""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Optional[ToolResult] = None


class AgentResult(BaseModel):
    """Agent runtime 对 service 层暴露的稳定结果。"""

    reply: str
    task_state: TaskState
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    tool_call_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    should_transfer: bool = False


def parse_tool_results_from_messages(messages: list[Any]) -> list[ToolResult]:
    """从 LangChain messages 中解析工具结果。"""
    results = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            results.append(ToolResult.from_tool_message(msg.content or ""))
    return results


def parse_tool_calls_from_messages(messages: list[Any]) -> list[ToolCallRecord]:
    """从 LangChain messages 中解析工具调用与结果记录。"""
    calls: list[ToolCallRecord] = []
    result_queue = parse_tool_results_from_messages(messages)

    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                calls.append(
                    ToolCallRecord(
                        name=tc.get("name", ""),
                        args=tc.get("args", {}) or {},
                    )
                )

    for index, result in enumerate(result_queue):
        if index < len(calls):
            calls[index].result = result
        else:
            calls.append(ToolCallRecord(name=result.tool, result=result))

    return calls
