"""Agent 状态定义 — LangGraph State 类型"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    LangGraph 的共享状态，在每个节点之间传递

    messages:      对话历史（user + assistant + tool 消息）
                   add_messages 保证新消息追加而不是覆盖
    user_id:       当前登录用户 ID（从 JWT 解析）
    conversation_id: 当前对话会话 ID
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: int
    conversation_id: int
