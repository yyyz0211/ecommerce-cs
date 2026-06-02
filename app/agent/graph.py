"""LangGraph Agent 图 — ReAct 循环：调 LLM → 判断 → 执行工具 → 循环"""

import json
from contextvars import ContextVar
from typing import Literal

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logger import agent_logger
from app.agent.state import AgentState
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import AGENT_TOOLS, execute_tool

# ContextVar 用于在协程之间传递 db session（LangGraph 节点内部可访问）
_db_context: ContextVar[AsyncSession] = ContextVar("db")

# DeepSeek 兼容 OpenAI SDK，只需设置 base_url
client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL,
)


def _tools_for_llm():
    """把 LangChain @tool 转为 OpenAI SDK 需要的 tools 格式"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.args_schema.schema() if t.args_schema else {},
            },
        }
        for t in AGENT_TOOLS
    ]


# ── 节点 1: 调用 LLM ──

async def call_llm_node(state: AgentState) -> dict:
    """把当前消息列表发给 LLM，获取回复或工具调用指令"""
    # 构建消息列表：System prompt（含用户上下文）+ 历史消息
    system_content = f"{SYSTEM_PROMPT}\n\n当前用户 ID：{state['user_id']}。用户已登录，不需要询问其身份。"
    api_messages = [{"role": "system", "content": system_content}]
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            api_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            entry = {"role": "assistant", "content": msg.content or ""}
            # 如果 AIMessage 有 tool_calls，必须传给 API，否则后续 ToolMessage 会报错
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

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=api_messages,
        tools=_tools_for_llm(),
    )

    ai_msg = response.choices[0].message

    # 记录 LLM 调用结果
    if ai_msg.tool_calls:
        tool_names = [tc.function.name for tc in ai_msg.tool_calls]
        agent_logger.info(f"LLM 决定调工具: {tool_names}")
    else:
        agent_logger.info(f"LLM 回复: {ai_msg.content[:80]}...")

    # 如果 LLM 要求调工具，构建 tool_calls 格式
    if ai_msg.tool_calls:
        lc_tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "args": json.loads(tc.function.arguments),
            }
            for tc in ai_msg.tool_calls
        ]
        return {"messages": [AIMessage(content=ai_msg.content or "", tool_calls=lc_tool_calls)]}

    # 无工具调用 → 直接文本回复
    return {"messages": [AIMessage(content=ai_msg.content)]}


# ── 路由判断: 继续执行工具还是结束 ──

def should_continue(state: AgentState) -> Literal["execute_tool", END]:
    """检查最后一条 AI 消息是否有 tool_calls"""
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "execute_tool"
    return END


# ── 节点 2: 执行工具 ──

async def execute_tool_node(state: AgentState) -> dict:
    """执行 LLM 请求的工具，将结果追加到消息列表"""
    last_msg = state["messages"][-1]
    db = _db_context.get()       # 从 ContextVar 取 db
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
        agent_logger.info(f"工具结果: {result[:80]}...")
        tool_messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

    return {"messages": tool_messages}


# ── 构建图 ──

def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("call_llm", call_llm_node)
    workflow.add_node("execute_tool", execute_tool_node)

    workflow.set_entry_point("call_llm")

    workflow.add_conditional_edges(
        "call_llm",
        should_continue,
        {"execute_tool": "execute_tool", END: END},
    )
    workflow.add_edge("execute_tool", "call_llm")  # 工具执行完回到 LLM 再生成回复

    return workflow.compile()


# 全局单例
agent_graph = build_agent_graph()
