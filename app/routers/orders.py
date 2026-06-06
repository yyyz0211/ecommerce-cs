"""订单路由：查询、创建、取消"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.order import (
    OrderCreateRequest,
    OrderItemResponse,
    OrderResponse,
    LogisticsResponse,
)
from app.services.auth_service import get_current_user
from app.services.order_service import (
    get_user_orders,
    get_order_detail,
    get_order_logistics,
    create_order,
    cancel_order,
)

router = APIRouter(prefix="/api/orders", tags=["订单"])


@router.get("")
async def list_orders(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(10, ge=1, le=100, description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的订单列表（分页）"""
    orders, total = await get_user_orders(db, current_user.id, page=page, size=size)
    return {
        "items": [OrderResponse.model_validate(o) for o in orders],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("", response_model=OrderResponse, status_code=201)
async def create_new_order(
    req: OrderCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新订单（调试用）"""
    items_data = [
        {"product_name": item.product_name, "quantity": item.quantity, "price": item.price}
        for item in req.items
    ]
    order = await create_order(
        db,
        user_id=current_user.id,
        items_data=items_data,
        shipping_address=req.shipping_address,
    )
    return order


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个订单详情（含商品明细）"""
    detail = await get_order_detail(db, order_id, current_user.id)
    order = detail["order"]
    items = detail["items"]
    response = OrderResponse.model_validate(order)
    response.items = [OrderItemResponse.model_validate(item) for item in items]
    return response


@router.patch("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_an_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消订单（仅 pending/paid 状态可取消）"""
    return await cancel_order(db, order_id, current_user.id)


@router.get("/{order_id}/logistics", response_model=LogisticsResponse)
async def get_logistics(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取订单物流信息"""
    return await get_order_logistics(db, order_id, current_user.id)
