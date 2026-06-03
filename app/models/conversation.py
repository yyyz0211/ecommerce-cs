"""对话相关模型：会话、消息、转人工记录、会话记忆"""

from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

MemoryTypeLiteral = Literal["summary", "task_state", "fact", "preference"]


class Conversation(Base):
    """对话会话"""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="用户 ID"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", comment="active/transferred/closed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="开始时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="最后活动时间"
    )


class Message(Base):
    """单条对话消息"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True, comment="会话 ID"
    )
    role: Mapped[str] = mapped_column(String(20), comment="user / agent")
    content: Mapped[str] = mapped_column(Text, comment="消息内容")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="发送时间"
    )


class ConversationMemory(Base):
    """会话记忆（摘要、偏好、事实、任务状态等）"""

    __tablename__ = "conversation_memories"
    __table_args__ = (
        UniqueConstraint("conversation_id", "memory_type", name="uq_conversation_memory_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True, comment="会话 ID"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="用户 ID"
    )
    memory_type: Mapped[MemoryTypeLiteral] = mapped_column(
        String(20), nullable=False, index=True, comment="summary / preference / fact / task_state"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="记忆内容")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )


class TransferLog(Base):
    """转人工记录"""

    __tablename__ = "transfer_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True, comment="会话 ID"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True, comment="用户 ID"
    )
    reason: Mapped[str] = mapped_column(Text, comment="转人工原因")
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="pending/processing/resolved"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="转接时间"
    )
