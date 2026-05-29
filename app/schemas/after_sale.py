"""售后相关 Pydantic 模型"""

from datetime import datetime

from pydantic import BaseModel, Field


class AfterSaleCreateRequest(BaseModel):
    """提交售后申请"""
    order_id: int = Field(..., description="关联订单 ID")
    type: str = Field(..., description="return / refund / exchange")
    reason: str = Field(..., min_length=1, max_length=500, description="售后原因")


class AfterSaleResponse(BaseModel):
    """售后记录响应"""
    id: int
    order_id: int
    user_id: int
    type: str
    reason: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
