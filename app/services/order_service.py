"""订单服务：查询、创建、取消订单"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError, ORDER_NOT_FOUND, LOGISTICS_NOT_FOUND
from app.models.order import Order, OrderItem, Logistics

_ALLOWED_CANCEL_STATUSES = {"pending", "paid"}
_ALLOWED_AFTER_SALE_STATUSES = {"paid", "shipped", "delivered"}


async def get_user_orders(
    db: AsyncSession, user_id: int, page: int = 1, size: int = 10
) -> tuple[list[Order], int]:
    """获取用户订单列表（分页），按时间倒序"""
    base_query = select(Order).where(Order.user_id == user_id)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.order_by(Order.created_at.desc()).offset((page - 1) * size).limit(size)
    )
    orders = result.scalars().all()
    return orders, total


async def get_order_detail(db: AsyncSession, order_id: int, user_id: int) -> dict:
    """获取单个订单详情（含商品明细），仅限本人订单"""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ORDER_NOT_FOUND

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    items = items_result.scalars().all()
    return {"order": order, "items": items}


async def get_order_logistics(db: AsyncSession, order_id: int, user_id: int) -> Logistics:
    """获取订单物流信息，仅限本人订单"""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ORDER_NOT_FOUND

    logistics_result = await db.execute(
        select(Logistics).where(Logistics.order_id == order_id)
    )
    logistics = logistics_result.scalar_one_or_none()
    if not logistics:
        raise LOGISTICS_NOT_FOUND
    return logistics


async def create_order(
    db: AsyncSession,
    user_id: int,
    items_data: list[dict],
    shipping_address: Optional[str] = None,
) -> Order:
    """创建新订单（调试/测试用，实际应由购物系统触发）"""
    order_no = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper()
    total_amount = sum(item["price"] * item["quantity"] for item in items_data)

    order = Order(
        user_id=user_id,
        order_no=order_no,
        total_amount=total_amount,
        shipping_address=shipping_address,
    )
    db.add(order)
    await db.flush()

    for item in items_data:
        db.add(OrderItem(
            order_id=order.id,
            product_name=item["product_name"],
            quantity=item["quantity"],
            price=item["price"],
        ))

    db.add(Logistics(order_id=order.id, status="待发货"))

    await db.commit()
    await db.refresh(order)
    return order


async def cancel_order(db: AsyncSession, order_id: int, user_id: int) -> Order:
    """取消订单 -- 仅 pending/paid 状态可取消"""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ORDER_NOT_FOUND

    if order.status not in _ALLOWED_CANCEL_STATUSES:
        raise AppError("ORDER_CANNOT_CANCEL", f"当前订单状态为 {order.status}，不可取消", 400)
    order.status = "cancelled"
    await db.commit()
    await db.refresh(order)
    return order
