"""对话相关模型：会话、消息、转人工记录"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Conversation(Base):
    """对话会话"""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True, comment="用户 ID")
    status: Mapped[str] = mapped_column(String(20), default="active", comment="active/transferred/closed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="开始时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="最后活动时间")


class Message(Base):
    """单条对话消息"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True, comment="会话 ID")
    role: Mapped[str] = mapped_column(String(20), comment="user / agent / system")
    content: Mapped[str] = mapped_column(Text, comment="消息内容")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="发送时间")


class TransferLog(Base):
    """转人工记录"""
    __tablename__ = "transfer_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True, comment="会话 ID")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True, comment="用户 ID")
    reason: Mapped[str] = mapped_column(Text, comment="转人工原因")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="pending/processing/resolved")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="转接时间")
