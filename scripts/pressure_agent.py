"""Run real Agent pressure scenarios and write a JSON trace report.

WARNING:
    This script calls the configured external LLM API and creates real local
    conversation / memory / after-sale data. Run it only against data and
    credentials that are allowed to leave the machine.

Examples:
    python scripts/pressure_agent.py --runs 30 --concurrency 10 --scenario memory
    python scripts/pressure_agent.py --runs 50 --concurrency 10 --scenario orders
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import logging
import statistics
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import select

from app.agent.core import graph as graph_module
from app.agent.core.runtime import run_agent
from app.agent.schemas.results import parse_tool_results_from_messages
from app.database import AsyncSessionLocal, engine
from app.models.conversation import Conversation
from app.models.user import User
from app.services.memory_service import save_conversation_memory

logging.getLogger("agent").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

TRACE_VAR = contextvars.ContextVar("agent_trace", default=None)
PATCH_INSTALLED = False
ORIGINAL_CLIENT = None

ORDER_SCENARIOS = [
    {"name": "logistics", "messages": [("user", "帮我查一下订单 202605280002 的物流")], "memory": {}},
    {"name": "detail", "messages": [("user", "查询订单 202605280001 的详情")], "memory": {}},
    {"name": "orders", "messages": [("user", "我有哪些订单？")], "memory": {}},
    {"name": "pending_logistics", "messages": [("user", "查一下订单 202605280003 的物流")], "memory": {}},
    {"name": "invalid_order", "messages": [("user", "帮我查一下不存在的订单 999999999999 的物流")], "memory": {}},
]

MEMORY_SCENARIOS = [
    {
        "name": "memory_reference_detail",
        "messages": [("user", "那这个订单详情呢？")],
        "memory": {
            "summary": "用户刚才在查询订单 202605280002 的物流。",
            "task_state": json.dumps(
                {
                    "version": 1,
                    "stage": "completed",
                    "intent": "query_logistics",
                    "status": "done",
                    "order_id": 11,
                    "customer_id": 6,
                    "confidence": 0.65,
                    "next_action": "reply_user",
                },
                ensure_ascii=False,
            ),
            "preference": "用户希望回答简洁。",
        },
    },
    {
        "name": "memory_conflict_latest_wins",
        "messages": [("user", "不要看刚才那个了，查订单 202605280001 的物流")],
        "memory": {"summary": "用户刚才在查询订单 202605280002 的物流。"},
    },
    {
        "name": "after_sale_complete",
        "messages": [("user", "订单 202605280001 我要退货，原因是手机壳尺寸不匹配")],
        "memory": {},
    },
    {
        "name": "after_sale_missing_reason",
        "messages": [("user", "订单 202605280002 我要退款")],
        "memory": {},
    },
    {"name": "smalltalk_no_tool", "messages": [("user", "你好，你能做什么？")], "memory": {}},
    {
        "name": "invalid_order_error_recovery",
        "messages": [("user", "帮我查一下不存在的订单 999999999999 的物流")],
        "memory": {},
    },
    {
        "name": "multi_turn_reference_detail",
        "messages": [
            ("user", "帮我查一下订单 202605280002 的物流"),
            ("agent", "订单 202605280002 的物流状态是运输中，快递单号 ZT9876543210。"),
            ("user", "那这个订单详情呢？"),
        ],
        "memory": {},
    },
    {
        "name": "memory_preference_concise",
        "messages": [("user", "查一下订单 202605280003 的物流")],
        "memory": {"preference": "用户希望回答非常简洁，只给结论。"},
    },
]


class TracedCompletions:
    def __init__(self, inner: Any):
        self._inner = inner

    async def create(self, *args, **kwargs):
        trace = TRACE_VAR.get()
        started = time.perf_counter()
        try:
            return await self._inner.create(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            if trace is not None:
                messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
                system_content = ""
                if messages and messages[0].get("role") == "system":
                    system_content = messages[0].get("content") or ""
                trace.append(
                    {
                        "node": "llm_api_request",
                        "elapsed_ms": round(elapsed_ms, 2),
                        "model": kwargs.get("model"),
                        "api_message_count": len(messages),
                        "system_prompt_memory_markers": {
                            "summary": "[会话摘要]" in system_content,
                            "task_state": "[当前任务状态]" in system_content,
                            "preference": "[用户偏好]" in system_content,
                            "fact": "[已知事实]" in system_content,
                        },
                        "system_prompt_preview": system_content[:1200],
                    }
                )


class TracedClient:
    def __init__(self, inner: Any):
        self.chat = type("TracedChat", (), {"completions": TracedCompletions(inner.chat.completions)})()


def install_trace_patch() -> None:
    global PATCH_INSTALLED, ORIGINAL_CLIENT
    if PATCH_INSTALLED:
        return
    original_call_llm = graph_module.call_llm_node
    original_execute_tool = graph_module.execute_tool_node
    original_get_client = graph_module.get_openai_client

    def traced_get_client():
        global ORIGINAL_CLIENT
        if ORIGINAL_CLIENT is None:
            ORIGINAL_CLIENT = original_get_client()
        return TracedClient(ORIGINAL_CLIENT)

    async def traced_call_llm(state):
        trace = TRACE_VAR.get()
        before_count = len(state.get("messages", []))
        started = time.perf_counter()
        result = await original_call_llm(state)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if trace is not None:
            produced = result.get("messages", [])
            event = {
                "node": "call_llm_node",
                "elapsed_ms": round(elapsed_ms, 2),
                "input_message_count": before_count,
                "assistant_messages": [],
                "task_state": None,
            }
            for msg in produced:
                if isinstance(msg, AIMessage):
                    event["assistant_messages"].append(
                        {"content": msg.content, "tool_calls": deepcopy(getattr(msg, "tool_calls", None) or [])}
                    )
            task_state = result.get("task_state")
            if task_state is not None:
                event["task_state"] = json.loads(task_state.model_dump_json())
            trace.append(event)
        return result

    async def traced_execute_tool(state):
        trace = TRACE_VAR.get()
        last_msg = state["messages"][-1]
        requested = deepcopy(getattr(last_msg, "tool_calls", None) or [])
        started = time.perf_counter()
        result = await original_execute_tool(state)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if trace is not None:
            produced = result.get("messages", [])
            parsed_results = parse_tool_results_from_messages(produced)
            trace.append(
                {
                    "node": "execute_tool_node",
                    "elapsed_ms": round(elapsed_ms, 2),
                    "requested_tool_calls": requested,
                    "tool_messages": [
                        {"tool_call_id": msg.tool_call_id, "content": msg.content}
                        for msg in produced
                        if isinstance(msg, ToolMessage)
                    ],
                    "parsed_tool_results": [json.loads(r.model_dump_json()) for r in parsed_results],
                    "task_state": json.loads(result["task_state"].model_dump_json()) if result.get("task_state") else None,
                }
            )
        return result

    graph_module.get_openai_client = traced_get_client
    graph_module.call_llm_node = traced_call_llm
    graph_module.execute_tool_node = traced_execute_tool
    graph_module._agent_graph = None
    PATCH_INSTALLED = True


async def get_user(db, username: str):
    return (await db.execute(select(User).where(User.username == username))).scalar_one()


async def create_conversation(db, user, memory: dict[str, str]):
    conversation = Conversation(user_id=user.id, status="active")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    for memory_type, content in memory.items():
        await save_conversation_memory(db, conversation.id, user.id, memory_type, content)
    return conversation


async def run_one(index: int, sem: asyncio.Semaphore, scenario: dict[str, Any], username: str):
    trace = []
    async with sem:
        started = time.perf_counter()
        token = TRACE_VAR.set(trace)
        try:
            async with AsyncSessionLocal() as db:
                user = await get_user(db, username)
                conversation = await create_conversation(db, user, scenario.get("memory", {}))
                message_likes = [
                    type("MessageLike", (), {"role": role, "content": content})()
                    for role, content in scenario["messages"]
                ]
                result = await run_agent(
                    db=db,
                    user=user,
                    conversation_id=conversation.id,
                    messages=message_likes,
                )
            return {
                "run": index,
                "scenario": scenario["name"],
                "ok": True,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "input_messages": scenario["messages"],
                "seeded_memory": scenario.get("memory", {}),
                "reply": result.reply,
                "tool_call_count": result.tool_call_count,
                "tool_calls": [json.loads(tc.model_dump_json()) for tc in result.tool_calls],
                "task_state": json.loads(result.task_state.model_dump_json()),
                "trace": trace,
            }
        except Exception as exc:
            return {
                "run": index,
                "scenario": scenario["name"],
                "ok": False,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "input_messages": scenario["messages"],
                "error_type": type(exc).__name__,
                "error": str(exc),
                "trace": trace,
            }
        finally:
            TRACE_VAR.reset(token)


def percentile(values: list[float], p: int):
    if not values:
        return None
    pos = min(len(values) - 1, int(round((p / 100) * (len(values) - 1))))
    return values[pos]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--scenario", choices=["orders", "memory"], default="memory")
    parser.add_argument("--username", default="buyer1")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    install_trace_patch()
    scenarios = MEMORY_SCENARIOS if args.scenario == "memory" else ORDER_SCENARIOS
    sem = asyncio.Semaphore(args.concurrency)
    started = time.perf_counter()
    results = await asyncio.gather(
        *(run_one(i, sem, scenarios[(i - 1) % len(scenarios)], args.username) for i in range(1, args.runs + 1))
    )
    elapsed = time.perf_counter() - started
    await engine.dispose()

    latencies = sorted(r["elapsed_ms"] for r in results)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "pressure": {
            "scenario": args.scenario,
            "total_runs": args.runs,
            "concurrency": args.concurrency,
            "success": sum(1 for r in results if r["ok"]),
            "errors": sum(1 for r in results if not r["ok"]),
            "elapsed_seconds": round(elapsed, 3),
            "throughput_rps": round(len(results) / elapsed, 2),
            "latency_ms": {
                "min": round(min(latencies), 2),
                "avg": round(statistics.mean(latencies), 2),
                "p50": round(percentile(latencies, 50), 2),
                "p95": round(percentile(latencies, 95), 2),
                "p99": round(percentile(latencies, 99), 2),
                "max": round(max(latencies), 2),
            },
        },
        "results": results,
    }
    out_path = Path(args.output or f"real_agent_pressure_{args.scenario}_{args.runs}x{args.concurrency}.json")
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"report_path": str(out_path), "pressure": payload["pressure"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
