"""对话相关 Pydantic 模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    """用户发送一条消息"""
    conversation_id: Optional[int] = None  # None 表示新建会话
    content: str


class ChatMessageResponse(BaseModel):
    """Agent 回复"""
    conversation_id: int
    reply: str


class ChatHistoryResponse(BaseModel):
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
