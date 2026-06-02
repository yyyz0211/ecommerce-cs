"""Agent 工具定义 — 封装现有 service 层为 LLM 可调用的工具"""

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.services.order_service import get_user_orders, get_order_detail, get_order_logistics
from app.services.after_sale_service import create_after_sale

# 工具执行时需要的上下文（db session 通过闭包注入）

@tool
def query_orders(user_id: str) -> str:
    """查用户订单列表。参数 user_id 为字符串形式的用户 ID。"""
    # 实际执行在 execute_tool_node 中处理，这里只是声明签名给 LLM 看
    return "Tool must be executed with db context"


@tool
def query_order_detail(user_id: str, order_id: str) -> str:
    """查订单详情，含商品明细。order_id 可以是数字 ID 或订单号（如 202605280001）。"""
    return "Tool must be executed with db context"


@tool
def query_logistics(user_id: str, order_id: str) -> str:
    """查订单物流信息。order_id 可以是数字 ID 或订单号。"""
    return "Tool must be executed with db context"


@tool
def submit_after_sale(order_id: str, type_: str, reason: str) -> str:
    """提交售后申请。order_id 可以是数字 ID 或订单号（如 202605280001）；
    type_ 为 return/refund/exchange，reason 为申请原因。"""
    return "Tool must be executed with db context"


# ── 辅助：智能解析 order_id（支持数字 ID 或订单号） ──

async def _resolve_order_id(db: AsyncSession, user_id: int, raw: str):
    """
    将 LLM 传来的 order_id 字符串解析为数据库数字 ID。
    先尝试 int() 直接转数字；失败则按订单号 (order_no) 模糊查库。
    返回 (order_id, error_message)，二选一非 None。
    """
    raw = raw.strip() if raw else ""
    if not raw:
        return None, "错误：订单 ID 为空，请提供有效的订单 ID 或订单号"

    # 优先尝试纯数字 ID
    try:
        return int(raw), None
    except ValueError:
        pass

    # 按订单号查找（用户的订单）
    result = await db.execute(
        select(Order).where(Order.order_no == raw, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if order:
        return order.id, None

    return None, f"错误：未找到订单 {raw}（该订单号不存在或不属于当前用户）"


# ── 工具执行器——由 graph 的 execute_tool_node 调用 ──

async def execute_tool(tool_name: str, tool_args: dict, db: AsyncSession, user_id: int) -> str:
    """根据工具名和参数执行对应的 service 函数，返回格式化文本结果"""

    if tool_name == "query_orders":
        orders, total = await get_user_orders(db, user_id)
        if not orders:
            return f"用户 {user_id} 目前没有订单"
        lines = [f"共 {total} 笔订单，请用 ID（不是订单号）查详情："]
        for o in orders:
            lines.append(f"  - ID={o.id} | {o.order_no} | {o.status} | ¥{o.total_amount}")
        return "\n".join(lines)

    elif tool_name == "query_order_detail":
        order_id, err = await _resolve_order_id(db, user_id, tool_args.get("order_id", ""))
        if err:
            return err
        detail = await get_order_detail(db, order_id, user_id)
        order = detail["order"]
        items = detail["items"]
        lines = [f"订单 {order.order_no} 详情：", f"  状态：{order.status}", f"  金额：¥{order.total_amount}"]
        if order.shipping_address:
            lines.append(f"  地址：{order.shipping_address}")
        lines.append("  商品：")
        for item in items:
            lines.append(f"    {item.product_name} x{item.quantity} ¥{item.price}")
        return "\n".join(lines)

    elif tool_name == "query_logistics":
        order_id, err = await _resolve_order_id(db, user_id, tool_args.get("order_id", ""))
        if err:
            return err
        logistics = await get_order_logistics(db, order_id, user_id)
        return (
            f"订单 {order_id} 物流：\n"
            f"  快递公司：{logistics.company or '未分配'}\n"
            f"  快递单号：{logistics.tracking_no or '暂无'}\n"
            f"  物流状态：{logistics.status}"
        )

    elif tool_name == "submit_after_sale":
        order_id, err = await _resolve_order_id(db, user_id, tool_args.get("order_id", ""))
        if err:
            return err
        type_ = tool_args.get("type_", "")
        reason = tool_args.get("reason", "")
        if not type_ or type_ not in ("return", "refund", "exchange"):
            return f"错误：无效的售后类型 {type_}，可选：return / refund / exchange"
        if not reason.strip():
            return "错误：请提供售后原因"
        record = await create_after_sale(db, user_id, order_id, type_, reason)
        return (
            f"售后申请已提交！\n"
            f"  售后编号：{record.id}\n"
            f"  类型：{record.type}\n"
            f"  状态：{record.status}"
        )

    else:
        return f"错误：未知工具 {tool_name}"


# 工具列表（给 LLM 看，帮助它决定调用哪个）
AGENT_TOOLS = [query_orders, query_order_detail, query_logistics, submit_after_sale]
