"""任务状态与记忆类型定义。

这里集中放置状态枚举和 `TaskState` schema，避免分散在多个服务里造成重复定义。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """会话记忆类型边界。"""

    # 长上下文压缩摘要，供后续对话恢复主题
    SUMMARY = "summary"
    # 当前业务流程状态，给 Agent 和持久化层共享
    TASK_STATE = "task_state"
    # 预留给长期事实记忆
    FACT = "fact"
    # 预留给偏好类记忆
    PREFERENCE = "preference"


class TaskStage(str, Enum):
    """任务阶段。"""

    NEW = "new"
    AWAITING_ORDER_ID = "awaiting_order_id"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskIntent(str, Enum):
    """用户意图。"""

    QUERY_ORDER_STATUS = "query_order_status"
    QUERY_LOGISTICS = "query_logistics"
    QUERY_AFTER_SALE = "query_after_sale"
    SUBMIT_AFTER_SALE = "submit_after_sale"
    CANCEL_ORDER = "cancel_order"
    TRANSFER_HUMAN = "transfer_human"
    OTHER = "other"


class TaskStatus(str, Enum):
    """任务整体状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ERROR = "error"


class NextAction(str, Enum):
    """下一步动作。"""

    ASK_USER_FOR_ORDER_ID = "ask_user_for_order_id"
    CONFIRM_USER_INTENT = "confirm_user_intent"
    CALL_BACKEND_API = "call_backend_api"
    REPLY_USER = "reply_user"
    TRANSFER_TO_HUMAN = "transfer_to_human"
    STOP = "stop"


class TaskState(BaseModel):
    """结构化任务状态。"""

    version: int = 1
    stage: TaskStage
    intent: TaskIntent
    status: TaskStatus
    order_id: Optional[int] = None
    customer_id: Optional[int] = None
    confidence: float = Field(ge=0.0, le=1.0)
    next_action: NextAction
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
