"""Agent 工具定义 — 封装现有 service 层为 LLM 可调用的工具"""

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas.results import ToolResult
from app.agent.schemas.task_state import TaskIntent, TaskStage, TaskStatus
from app.errors import AppError
from app.models.order import Order
from app.services.order_service import get_user_orders, get_order_detail, get_order_logistics
from app.services.after_sale_service import create_after_sale

# 工具执行时需要的上下文（db session 通过闭包注入）

@tool
def query_orders() -> str:
    """查当前用户的订单列表。"""
    # 实际执行在 execute_tool_node 中处理，这里只是声明签名给 LLM 看
    return "Tool must be executed with db context"


@tool
def query_order_detail(order_id: str) -> str:
    """查订单详情，含商品明细。order_id 可以是数字 ID 或订单号（如 202605280001）。"""
    return "Tool must be executed with db context"


@tool
def query_logistics(order_id: str) -> str:
    """查订单物流信息。order_id 可以是数字 ID 或订单号。"""
    return "Tool must be executed with db context"


@tool
def submit_after_sale(order_id: str, sale_type: str, reason: str) -> str:
    """提交售后申请。order_id 可以是数字 ID 或订单号（如 202605280001）；
    sale_type 为 return/refund/exchange，reason 为申请原因。"""
    return "Tool must be executed with db context"


# ── 辅助：智能解析 order_id（支持数字 ID 或订单号） ──

async def _resolve_order_id(db: AsyncSession, user_id: int, raw: str):
    """
    将 LLM 传来的 order_id 字符串解析为数据库数字 ID。
    优先按订单号 (order_no) 查找；找不到时再尝试按数据库数字 ID 查找。
    返回 (order_id, error_message)，二选一非 None。
    """
    raw = raw.strip() if raw else ""
    if not raw:
        return None, "错误：订单 ID 为空，请提供有效的订单 ID 或订单号"

    # 订单号可能是纯数字（例如 202605280001），所以必须先按 order_no 查。
    result = await db.execute(
        select(Order).where(Order.order_no == raw, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if order:
        return order.id, None

    try:
        order_id = int(raw)
    except ValueError:
        return None, f"错误：未找到订单 {raw}（该订单号不存在或不属于当前用户）"

    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if order:
        return order.id, None

    return None, f"错误：未找到订单 {raw}（该订单 ID/订单号不存在或不属于当前用户）"


# ── 工具执行器——由 graph 的 execute_tool_node 调用 ──

async def execute_tool(tool_name: str, tool_args: dict, db: AsyncSession, user_id: int) -> ToolResult:
    """根据工具名和参数执行对应的 service 函数，返回结构化工具结果。"""
    try:
        return await _execute_tool(tool_name, tool_args, db, user_id)
    except AppError as exc:
        return ToolResult(
            ok=False,
            tool=tool_name,
            message=f"错误：{exc.message}",
            error_code=exc.code,
            task_patch={
                "stage": TaskStage.FAILED.value,
                "intent": _intent_for_tool(tool_name).value,
                "status": TaskStatus.ERROR.value,
            },
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            tool=tool_name,
            message=f"错误：工具执行失败（{type(exc).__name__}）",
            error_code="TOOL_EXECUTION_ERROR",
            task_patch={
                "stage": TaskStage.FAILED.value,
                "intent": _intent_for_tool(tool_name).value,
                "status": TaskStatus.ERROR.value,
            },
        )


async def _execute_tool(tool_name: str, tool_args: dict, db: AsyncSession, user_id: int) -> ToolResult:
    """执行具体工具逻辑。"""

    if tool_name == "query_orders":
        orders, total = await get_user_orders(db, user_id)
        if not orders:
            return ToolResult(
                ok=True,
                tool=tool_name,
                message="您目前没有订单。",
                data={"orders": [], "total": total},
                task_patch={
                    "stage": TaskStage.COMPLETED.value,
                    "intent": TaskIntent.QUERY_ORDER_STATUS.value,
                    "status": TaskStatus.DONE.value,
                },
            )
        lines = [f"共 {total} 笔订单，请用 ID（不是订单号）查详情："]
        order_data = []
        for o in orders:
            lines.append(f"  - ID={o.id} | {o.order_no} | {o.status} | ¥{o.total_amount}")
            order_data.append({
                "id": o.id,
                "order_no": o.order_no,
                "status": o.status,
                "total_amount": float(o.total_amount),
            })
        return ToolResult(
            ok=True,
            tool=tool_name,
            message="\n".join(lines),
            data={"orders": order_data, "total": total},
            task_patch={
                "stage": TaskStage.COMPLETED.value,
                "intent": TaskIntent.QUERY_ORDER_STATUS.value,
                "status": TaskStatus.DONE.value,
            },
        )

    elif tool_name == "query_order_detail":
        order_id, err = await _resolve_order_id(db, user_id, tool_args.get("order_id", ""))
        if err:
            return _tool_error(tool_name, err, TaskIntent.QUERY_ORDER_STATUS)
        detail = await get_order_detail(db, order_id, user_id)
        order = detail["order"]
        items = detail["items"]
        lines = [f"订单 {order.order_no} 详情：", f"  状态：{order.status}", f"  金额：¥{order.total_amount}"]
        if order.shipping_address:
            lines.append(f"  地址：{order.shipping_address}")
        lines.append("  商品：")
        for item in items:
            lines.append(f"    {item.product_name} x{item.quantity} ¥{item.price}")
        return ToolResult(
            ok=True,
            tool=tool_name,
            message="\n".join(lines),
            data={
                "order_id": order.id,
                "order_no": order.order_no,
                "status": order.status,
                "total_amount": float(order.total_amount),
                "shipping_address": order.shipping_address,
                "items": [
                    {
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "price": float(item.price),
                    }
                    for item in items
                ],
            },
            task_patch={
                "stage": TaskStage.COMPLETED.value,
                "intent": TaskIntent.QUERY_ORDER_STATUS.value,
                "status": TaskStatus.DONE.value,
                "order_id": order.id,
            },
        )

    elif tool_name == "query_logistics":
        order_id, err = await _resolve_order_id(db, user_id, tool_args.get("order_id", ""))
        if err:
            return _tool_error(tool_name, err, TaskIntent.QUERY_LOGISTICS)
        logistics = await get_order_logistics(db, order_id, user_id)
        message = (
            f"订单 {order_id} 物流：\n"
            f"  快递公司：{logistics.company or '未分配'}\n"
            f"  快递单号：{logistics.tracking_no or '暂无'}\n"
            f"  物流状态：{logistics.status}"
        )
        return ToolResult(
            ok=True,
            tool=tool_name,
            message=message,
            data={
                "order_id": order_id,
                "company": logistics.company,
                "tracking_no": logistics.tracking_no,
                "status": logistics.status,
            },
            task_patch={
                "stage": TaskStage.COMPLETED.value,
                "intent": TaskIntent.QUERY_LOGISTICS.value,
                "status": TaskStatus.DONE.value,
                "order_id": order_id,
            },
        )

    elif tool_name == "submit_after_sale":
        order_id, err = await _resolve_order_id(db, user_id, tool_args.get("order_id", ""))
        if err:
            return _tool_error(tool_name, err, TaskIntent.SUBMIT_AFTER_SALE)
        sale_type = tool_args.get("sale_type") or tool_args.get("type_") or tool_args.get("type") or ""
        reason = tool_args.get("reason", "")
        if not sale_type or sale_type not in ("return", "refund", "exchange"):
            return _tool_error(
                tool_name,
                f"错误：无效的售后类型 {sale_type}，可选：return / refund / exchange",
                TaskIntent.SUBMIT_AFTER_SALE,
            )
        if not reason.strip():
            return _tool_error(tool_name, "错误：请提供售后原因", TaskIntent.SUBMIT_AFTER_SALE)
        record = await create_after_sale(db, user_id, order_id, sale_type, reason)
        message = (
            f"售后申请已提交！\n"
            f"  售后编号：{record.id}\n"
            f"  类型：{record.type}\n"
            f"  状态：{record.status}"
        )
        return ToolResult(
            ok=True,
            tool=tool_name,
            message=message,
            data={
                "after_sale_id": record.id,
                "order_id": order_id,
                "type": record.type,
                "status": record.status,
            },
            task_patch={
                "stage": TaskStage.COMPLETED.value,
                "intent": TaskIntent.SUBMIT_AFTER_SALE.value,
                "status": TaskStatus.DONE.value,
                "order_id": order_id,
            },
        )

    else:
        return _tool_error(tool_name, f"错误：未知工具 {tool_name}", TaskIntent.OTHER, "UNKNOWN_TOOL")


def _tool_error(
    tool_name: str,
    message: str,
    intent: TaskIntent,
    error_code: str = "TOOL_INPUT_ERROR",
) -> ToolResult:
    return ToolResult(
        ok=False,
        tool=tool_name,
        message=message,
        error_code=error_code,
        task_patch={
            "stage": TaskStage.FAILED.value,
            "intent": intent.value,
            "status": TaskStatus.ERROR.value,
        },
    )


def _intent_for_tool(tool_name: str) -> TaskIntent:
    return {
        "query_orders": TaskIntent.QUERY_ORDER_STATUS,
        "query_order_detail": TaskIntent.QUERY_ORDER_STATUS,
        "query_logistics": TaskIntent.QUERY_LOGISTICS,
        "submit_after_sale": TaskIntent.SUBMIT_AFTER_SALE,
    }.get(tool_name, TaskIntent.OTHER)


# 工具列表（给 LLM 看，帮助它决定调用哪个）
AGENT_TOOLS = [query_orders, query_order_detail, query_logistics, submit_after_sale]
