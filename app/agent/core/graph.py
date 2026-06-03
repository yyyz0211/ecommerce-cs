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
from typing import Literal

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI

from app.config import settings
from app.logger import agent_logger
from app.agent.schemas.state import AgentState
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.core.confidence import calculate_confidence
from app.agent.schemas.results import parse_tool_results_from_messages
from app.agent.core.state_machine import reduce_task_state
from app.agent.schemas.task_state import (
    MemoryType,
    NextAction,
    TaskIntent,
    TaskStage,
    TaskState,
    TaskStatus,
)
from app.agent.tools import AGENT_TOOLS, execute_tool

# DeepSeek 兼容 OpenAI SDK，只需设置 base_url
client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL,
)


def _tools_for_llm():
    """将 LangChain 工具转成 OpenAI SDK 可直接消费的 schema。

    这里保持和工具定义完全一致，避免人工维护两份参数结构。"""
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


def _format_memory_for_prompt(memory: dict) -> str:
    """按记忆类型分层拼装 prompt，避免把不同语义的记忆混成一段。"""
    sections = []

    summary = memory.get(MemoryType.SUMMARY.value)
    if summary:
        sections.append(f"[会话摘要]\n{summary}")

    task_state = memory.get(MemoryType.TASK_STATE.value)
    if task_state:
        try:
            task_state_text = json.dumps(json.loads(task_state), ensure_ascii=False, indent=2)
        except (TypeError, json.JSONDecodeError):
            task_state_text = str(task_state)
        sections.append(f"[当前任务状态]\n{task_state_text}")

    preference = memory.get(MemoryType.PREFERENCE.value)
    if preference:
        sections.append(f"[用户偏好]\n{preference}")

    fact = memory.get(MemoryType.FACT.value)
    if fact:
        sections.append(f"[已知事实]\n{fact}")

    return "\n\n".join(sections)


async def load_memory_node(state: AgentState) -> dict:
    """从 DB 加载会话记忆到 state.memory。

    记忆在图内只读，不在这里做写入；写入由 services 层统一处理。"""
    from app.services.memory_service import get_conversation_memory

    db = state["db"]
    memories = await get_conversation_memory(db, state["conversation_id"], state["user_id"])
    memory: dict = {}
    for m in memories:
        if m.content:
            memory[m.memory_type] = m.content
    if memory:
        agent_logger.info(f"加载记忆: {list(memory.keys())}")
    return {"memory": memory}


# ── 节点 1: 调用 LLM ──

async def call_llm_node(state: AgentState) -> dict:
    """把当前消息列表发给 LLM，获取回复或工具调用指令。"""
    memory = state.get("memory", {})
    memory_text = _format_memory_for_prompt(memory) if memory else ""
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

    request_kwargs = {
        "model": settings.LLM_MODEL,
        "messages": api_messages,
    }
    if state.get("tool_call_count", 0) == 0:
        request_kwargs["tools"] = _tools_for_llm()

    response = await client.chat.completions.create(**request_kwargs)

    ai_msg = response.choices[0].message

    # 记录 LLM 调用结果
    if ai_msg.tool_calls:
        tool_names = [tc.function.name for tc in ai_msg.tool_calls]
        agent_logger.info(f"LLM 决定调工具: {tool_names}")
    else:
        # 纯文本回复时记录首段内容，方便排查模型输出是否异常
        agent_logger.info(f"LLM 回复: {(ai_msg.content or '')[:80]}...")

    # 如果 LLM 要求调工具，构建 tool_calls 格式
    if ai_msg.tool_calls:
        tool_calls = list(ai_msg.tool_calls)
        if len(tool_calls) > 1:
            agent_logger.info(f"模型一次请求了 {len(tool_calls)} 个工具，仅执行第一个")
            tool_calls = tool_calls[:1]
        lc_tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "args": json.loads(tc.function.arguments),
            }
            for tc in tool_calls
        ]
        return {"messages": [AIMessage(content=ai_msg.content or "", tool_calls=lc_tool_calls)]}

    return {
        "messages": [AIMessage(content=ai_msg.content or "")],
        "task_state": _build_task_state(state),
    }

# ── 路由判断: 继续执行工具还是结束 ──

def should_continue(state: AgentState) -> Literal["execute_tool", END]:
    """如果最后一条 AI 消息带有 tool_calls，就继续执行工具。"""
    if state.get("tool_call_count", 0) >= 1:
        return END
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "execute_tool"
    return END


# ── 节点 2: 执行工具 ──

async def execute_tool_node(state: AgentState) -> dict:
    """执行 LLM 请求的工具，将结果追加到消息列表。"""
    last_msg = state["messages"][-1]
    db = state["db"]
    user_id = state["user_id"]

    tool_messages = []
    executed_count = 0
    for tc in last_msg.tool_calls:
        if state.get("tool_call_count", 0) + executed_count >= 1:
            agent_logger.info(f"跳过工具 {tc['name']}：当前轮已执行过工具")
            continue
        agent_logger.info(f"执行工具: {tc['name']}({tc['args']})")
        result = await execute_tool(
            tool_name=tc["name"],
            tool_args=tc["args"],
            db=db,
            user_id=user_id,
        )
        # 工具返回内容只记录前缀，避免日志被大段响应撑爆
        agent_logger.info(f"工具结果: {result.message_for_log(80)}...")
        tool_messages.append(ToolMessage(content=result.to_tool_message(), tool_call_id=tc["id"]))
        executed_count += 1

    return {
        "messages": tool_messages,
        "tool_call_count": state.get("tool_call_count", 0) + executed_count,
    }


def _build_task_state(state: AgentState) -> TaskState:
    """根据当前消息与工具执行情况，生成一个保底的结构化任务状态。

    这是过渡逻辑：优先保证 task_state 始终可落库，再逐步演进到更细的状态推断。"""
    has_structured_tool_result = any(
        isinstance(msg, ToolMessage) and (msg.content or "").strip().startswith("{")
        for msg in state.get("messages", [])
    )
    if has_structured_tool_result:
        parsed_results = parse_tool_results_from_messages(state.get("messages", []))
        return reduce_task_state(
            user_id=state["user_id"],
            old_state=state.get("task_state"),
            messages=state.get("messages", []),
            tool_results=parsed_results,
        )

    last_user_message = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break

    tool_names = []
    tool_results = []
    for msg in state.get("messages", []):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            tool_names.extend(tc["name"] for tc in msg.tool_calls)
        elif isinstance(msg, ToolMessage):
            tool_results.append(msg.content or "")

    has_tool_error = any(result.startswith("错误") for result in tool_results)
    if has_tool_error:
        stage = TaskStage.FAILED
        intent = TaskIntent.OTHER
        next_action = NextAction.REPLY_USER
        task_status = TaskStatus.ERROR
    elif "submit_after_sale" in tool_names:
        stage = TaskStage.COMPLETED
        intent = TaskIntent.SUBMIT_AFTER_SALE
        next_action = NextAction.REPLY_USER
        task_status = TaskStatus.DONE
    elif "query_logistics" in tool_names:
        stage = TaskStage.COMPLETED
        intent = TaskIntent.QUERY_LOGISTICS
        next_action = NextAction.REPLY_USER
        task_status = TaskStatus.DONE
    elif "query_order_detail" in tool_names or "query_orders" in tool_names:
        stage = TaskStage.COMPLETED
        intent = TaskIntent.QUERY_ORDER_STATUS
        next_action = NextAction.REPLY_USER
        task_status = TaskStatus.DONE
    elif "订单" in last_user_message or "物流" in last_user_message:
        stage = TaskStage.AWAITING_ORDER_ID
        intent = TaskIntent.QUERY_LOGISTICS if "物流" in last_user_message else TaskIntent.QUERY_ORDER_STATUS
        next_action = NextAction.ASK_USER_FOR_ORDER_ID
        task_status = TaskStatus.PENDING
    else:
        stage = TaskStage.NEW
        intent = TaskIntent.OTHER
        next_action = NextAction.REPLY_USER
        task_status = TaskStatus.PENDING

    # 过渡阶段先用规则/上下文得到一个保底分，后续可以继续接入模型概率与规则分数
    confidence = calculate_confidence(
        model_prob=0.5,
        rule_score=0.5 if tool_names else 0.3,
        context_score=0.8 if last_user_message else 0.2,
    )

    return TaskState(
        stage=stage,
        intent=intent,
        status=task_status,
        customer_id=state["user_id"],
        confidence=confidence,
        next_action=next_action,
    )


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


# 全局单例
agent_graph = build_agent_graph()
