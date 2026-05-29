"""订单相关模型：订单、订单商品、物流"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, DECIMAL, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True, comment="用户 ID")
    order_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="订单编号")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="pending/paid/shipped/delivered/cancelled")
    total_amount: Mapped[float] = mapped_column(DECIMAL(10, 2), comment="订单金额")
    shipping_address: Mapped[Optional[str]] = mapped_column(String(255), comment="收货地址（下单时快照）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="下单时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # TODO(later): 添加 relationship，方便通过 order.user 拿到用户信息
    # user: Mapped["User"] = relationship(back_populates="orders")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True, comment="订单 ID")
    product_name: Mapped[str] = mapped_column(String(200), comment="商品名称")
    quantity: Mapped[int] = mapped_column(Integer, comment="数量")
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), comment="单价")


class Logistics(Base):
    __tablename__ = "logistics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True, comment="订单 ID")
    company: Mapped[Optional[str]] = mapped_column(String(50), comment="快递公司")
    tracking_no: Mapped[Optional[str]] = mapped_column(String(100), comment="快递单号")
    status: Mapped[str] = mapped_column(String(50), default="pending", comment="物流状态")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="最新更新时间")
