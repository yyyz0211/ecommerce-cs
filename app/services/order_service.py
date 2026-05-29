"""订单服务：查询、创建、取消订单"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem, Logistics


# ── 订单状态机：每种状态下允许的操作 ──
# TODO(later): 迁移到独立的状态管理模块，避免硬编码
_ALLOWED_CANCEL_STATUSES = {"pending", "paid"}
_ALLOWED_AFTER_SALE_STATUSES = {"paid", "shipped", "delivered"}


def get_user_orders(
    db: Session, user_id: int, page: int = 1, size: int = 10
) -> tuple[list[Order], int]:
    """获取用户订单列表（分页），按时间倒序"""
    query = db.query(Order).filter(Order.user_id == user_id)
    total = query.count()
    orders = (
        query.order_by(Order.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return orders, total


def get_order_detail(db: Session, order_id: int, user_id: int) -> dict:
    """获取单个订单详情（含商品明细），仅限本人订单"""
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    return {"order": order, "items": items}


def get_order_logistics(db: Session, order_id: int, user_id: int) -> Logistics:
    """获取订单物流信息，仅限本人订单"""
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    logistics = db.query(Logistics).filter(Logistics.order_id == order_id).first()
    if not logistics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无物流信息")
    return logistics


def create_order(
    db: Session,
    user_id: int,
    items_data: list[dict],
    shipping_address: Optional[str] = None,
) -> Order:
    """创建新订单（调试/测试用，实际应由购物系统触发）"""
    # 生成唯一订单号
    order_no = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper()
    total_amount = sum(item["price"] * item["quantity"] for item in items_data)

    order = Order(
        user_id=user_id,
        order_no=order_no,
        total_amount=total_amount,
        shipping_address=shipping_address,
    )
    db.add(order)
    db.flush()  # 获取 order.id

    # 写入商品明细
    for item in items_data:
        db.add(OrderItem(
            order_id=order.id,
            product_name=item["product_name"],
            quantity=item["quantity"],
            price=item["price"],
        ))

    # 创建占位物流记录
    db.add(Logistics(order_id=order.id, status="待发货"))

    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order_id: int, user_id: int) -> Order:
    """取消订单 -- 仅 pending/paid 状态可取消"""
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    # 状态校验：已发货/已签收的订单不能取消
    if order.status not in _ALLOWED_CANCEL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前订单状态为 {order.status}，不可取消",
        )
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return order
