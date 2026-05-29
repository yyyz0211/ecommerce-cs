"""用户模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, comment="用户名")
    password_hash: Mapped[str] = mapped_column(String(255), comment="密码哈希")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="手机号")
    default_address: Mapped[Optional[str]] = mapped_column(String(255), comment="默认收货地址")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="注册时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # TODO(later): 添加 relationship，方便 user.orders 直接拿到订单列表
    # orders: Mapped[list["Order"]] = relationship(back_populates="user")
