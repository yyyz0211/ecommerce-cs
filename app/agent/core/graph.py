"""LangGraph Agent 图 — ReAct 循环

图结构:
  START → load_memory → call_llm ──┬── 有 tool_call ──→ execute_tool ──┐
                                   │                                  │
                                   └── 无 tool_call ──→ END           │
                                                                      │
                                            ←─────────────────────────┘
                                              (回到 call_llm 继续)
"""

import json
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI

from app.config import settings
from app.logger import agent_logger
from app.agent.schemas.state import AgentState
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.core.state_machine import reduce_task_state
from app.agent.schemas.task_state import MemoryType
from app.agent.tools import AGENT_TOOLS, execute_tool

_client: Optional[AsyncOpenAI] = None
_agent_graph = None


def get_openai_client() -> AsyncOpenAI:
    """延迟创建 LLM client，避免 import 阶段依赖配置完整性。"""
    global _client
    if _client is None:
        # DeepSeek 兼容 OpenAI SDK，只需设置 base_url
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
    return _client


def _tools_for_llm():
    """将 LangChain 工具转成 OpenAI SDK 可直接消费的 schema。

    这里保持和工具定义完全一致，避免人工维护两份参数结构。"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.args_schema.model_json_schema() if t.args_schema else {},
            },
        }
        for t in AGENT_TOOLS
    ]


def _format_memory_for_prompt(memory_map: dict) -> str:
    """按记忆类型分层拼装 prompt，避免把不同语义的记忆混成一段。
    提示词事例：
        [会话摘要]
        用户最近在查订单和物流。

        [当前任务状态]
        { }

        [用户偏好]
        用户希望简洁回答。

        [已知事实]
        用户的默认地址在上海。
    """
    sections = []

    summary = memory_map.get(MemoryType.SUMMARY.value)
    if summary:
        sections.append(f"[会话摘要]\n{summary}")

    task_state = memory_map.get(MemoryType.TASK_STATE.value)
    if task_state:
        try:
            task_state_text = json.dumps(json.loads(task_state), ensure_ascii=False, indent=2)
        except (TypeError, json.JSONDecodeError):
            task_state_text = str(task_state)
        sections.append(f"[当前任务状态]\n{task_state_text}")

    preference = memory_map.get(MemoryType.PREFERENCE.value)
    if preference:
        sections.append(f"[用户偏好]\n{preference}")

    fact = memory_map.get(MemoryType.FACT.value)
    if fact:
        sections.append(f"[已知事实]\n{fact}")

    return "\n\n".join(sections)


async def load_memory_node(state: AgentState) -> dict:
    """从 DB 加载会话记忆到 state.memory。

    记忆在图内只读，不在这里做写入；写入由 services 层统一处理。"""
    from app.services.memory_service import get_conversation_memory

    db = state["db"]
    memories = await get_conversation_memory(db, state["conversation_id"], state["user_id"])
    memory_map: dict = {}
    for item in memories:
        if item.content:
            memory_map[item.memory_type] = item.content
    if memory_map:
        agent_logger.info(f"加载记忆: {list(memory_map.keys())}")
    return {"memory": memory_map}


# ── 节点 1: 调用 LLM ──

async def call_llm_node(state: AgentState) -> dict:
    """把当前消息列表发给 LLM，获取回复或工具调用指令。
    
    提示词事例：
        system:
        {SYSTEM_PROMPT}

        [会话记忆]
        [会话摘要]
        ...

        [当前任务状态]
        ...

        [用户偏好]
        ...

        [已知事实]
        ...

        当前用户 ID：{state['user_id']}。
    """
    memory_map = state.get("memory", {})
    memory_text = _format_memory_for_prompt(memory_map) if memory_map else ""
    if memory_text:
        system_content = f"{SYSTEM_PROMPT}\n\n[会话记忆]\n{memory_text}\n\n当前用户 ID：{state['user_id']}。"
    else:
        system_content = f"{SYSTEM_PROMPT}\n\n当前用户 ID：{state['user_id']}。"
    api_messages = [{"role": "system", "content": system_content}]
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            api_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            entry = {"role": "assistant", "content": msg.content or ""}
            # tool_calls 必须原样传回去，否则后面的 ToolMessage 无法被模型正确关联
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["args"], ensure_ascii=False)},
                    }
                    for tc in msg.tool_calls
                ]
            api_messages.append(entry)
        elif isinstance(msg, ToolMessage):
            api_messages.append({"role": "tool", "content": msg.content, "tool_call_id": msg.tool_call_id})

    response = await get_openai_client().chat.completions.create(
        model=settings.LLM_MODEL,
        messages=api_messages,
        tools=_tools_for_llm(),
    )

    ai_msg = response.choices[0].message

    # 记录 LLM 调用结果
    if ai_msg.tool_calls:
        tool_names = [tc.function.name for tc in ai_msg.tool_calls]
        agent_logger.info(f"LLM 决定调工具: {tool_names}")
        lc_tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "args": json.loads(tc.function.arguments),
            }
            for tc in ai_msg.tool_calls
        ]
        return {"messages": [AIMessage(content=ai_msg.content or "", tool_calls=lc_tool_calls)]}

    agent_logger.info(f"LLM 回复: {(ai_msg.content or '')[:80]}...")
    next_messages = state["messages"] + [AIMessage(content=ai_msg.content or "")]
    return {
        "messages": [AIMessage(content=ai_msg.content or "")],
        "task_state": reduce_task_state(
            user_id=state["user_id"],
            old_state=state.get("task_state"),
            messages=next_messages,
        ),
    }

# ── 路由判断: 继续执行工具还是结束 ──

def should_continue(state: AgentState) -> Literal["execute_tool", END]:
    """如果最后一条 AI 消息带有 tool_calls，就继续执行工具。"""
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "execute_tool"
    return END


# ── 节点 2: 执行工具 ──

async def execute_tool_node(state: AgentState) -> dict:
    """执行 LLM 请求的工具，将结果追加到消息列表。
    
    输入: state.messages[-1].tool_calls（LLM 请求的工具列表）
    
    循环处理每个 tool_call：
    
    工具执行: result = await execute_tool(tool_name, tool_args, db, user_id)
    结果追加: tool_messages.append(ToolMessage(content=result.to_tool_message(), tool_call_id=tool_call.id))
    """
    last_msg = state["messages"][-1]
    db = state["db"]
    user_id = state["user_id"]

    tool_messages = []
    for tc in last_msg.tool_calls:
        agent_logger.info(f"执行工具: {tc['name']}({tc['args']})")
        result = await execute_tool(
            tool_name=tc["name"],
            tool_args=tc["args"],
            db=db,
            user_id=user_id,
        )
        agent_logger.info(f"工具结果: {result.message_for_log(80)}...")
        tool_messages.append(ToolMessage(content=result.to_tool_message(), tool_call_id=tc["id"]))

    next_messages = state["messages"] + tool_messages
    return {
        "messages": tool_messages,
        "task_state": reduce_task_state(
            user_id=state["user_id"],
            old_state=state.get("task_state"),
            messages=next_messages,
        ),
    }


def build_agent_graph() -> StateGraph:
    """构建并编译 LangGraph。"""
    workflow = StateGraph(AgentState)

    workflow.add_node("load_memory", load_memory_node)
    workflow.add_node("call_llm", call_llm_node)
    workflow.add_node("execute_tool", execute_tool_node)

    workflow.set_entry_point("load_memory")
    workflow.add_edge("load_memory", "call_llm")

    workflow.add_conditional_edges(
        "call_llm",
        should_continue,
        {"execute_tool": "execute_tool", END: END},
    )
    workflow.add_edge("execute_tool", "call_llm")

    return workflow.compile()


def get_agent_graph():
    """延迟构建 LangGraph，降低导入模块时的配置/依赖耦合。"""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
