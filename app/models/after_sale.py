"""售后模型"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AfterSale(Base):
    __tablename__ = "after_sales"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True, comment="关联订单")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True, comment="用户 ID")
    type: Mapped[str] = mapped_column(String(20), comment="return/refund/exchange")
    reason: Mapped[str] = mapped_column(Text, comment="售后原因")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="pending/approved/rejected/completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="申请时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
