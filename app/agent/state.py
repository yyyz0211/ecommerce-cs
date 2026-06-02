"""Agent 状态定义 — LangGraph State 类型

AgentState 在图的每个节点之间传递，每个节点返回一个 dict，
LangGraph 根据字段的 Annotated reducer 决定如何合并更新:
  - messages: add_messages → 追加到列表末尾
  - user_id / conversation_id / memory: 无 reducer → 直接覆盖
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    LangGraph 共享状态，节点返回的 dict 只包含需要更新的字段。

    messages
        对话历史（user + assistant + tool），add_messages 保证追加而非覆盖。
        例如节点 return {"messages": [AIMessage(...)]} 会把新消息加到列表末尾。

    user_id / conversation_id
        来自 JWT 和路由层，图内节点只读不写。

    memory
        会话记忆快照（dict，key 为 memory_type，value 为 content）。
        load_memory 节点从 DB 加载后写入，call_llm 注入 system prompt。
        图内节点不再修改它——写入由 process_agent_message 的后台任务异步执行。
        字段无 Annotated reducer → 每次更新是全量覆盖。
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: int
    conversation_id: int
    memory: dict
