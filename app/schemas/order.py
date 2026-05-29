"""订单相关 Pydantic 模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrderItemCreate(BaseModel):
    """创建订单时的商品项"""
    product_name: str = Field(..., max_length=200)
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)


class OrderCreateRequest(BaseModel):
    """创建订单请求"""
    items: list[OrderItemCreate] = Field(..., min_length=1, description="商品列表")
    shipping_address: Optional[str] = Field(None, max_length=255, description="收货地址")


class OrderItemResponse(BaseModel):
    product_name: str
    quantity: int
    price: float

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    order_no: str
    status: str
    total_amount: float
    shipping_address: Optional[str] = None
    created_at: datetime
    items: Optional[list[OrderItemResponse]] = None

    model_config = {"from_attributes": True}


class LogisticsResponse(BaseModel):
    company: Optional[str]
    tracking_no: Optional[str]
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}
