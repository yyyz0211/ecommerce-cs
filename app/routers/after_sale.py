"""售后路由：提交申请、查询记录"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.after_sale import AfterSaleCreateRequest, AfterSaleResponse
from app.services.auth_service import get_current_user
from app.services.after_sale_service import (
    create_after_sale,
    get_user_after_sales,
    get_after_sale_detail,
)

router = APIRouter(prefix="/api/after-sales", tags=["售后"])


@router.post("", response_model=AfterSaleResponse, status_code=201)
async def submit_after_sale(
    req: AfterSaleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交售后申请"""
    return await create_after_sale(
        db, user_id=current_user.id, order_id=req.order_id, type_=req.type, reason=req.reason,
    )


@router.get("", response_model=list[AfterSaleResponse])
async def list_after_sales(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看我的售后列表"""
    return await get_user_after_sales(db, current_user.id)


@router.get("/{after_sale_id}", response_model=AfterSaleResponse)
async def get_after_sale(
    after_sale_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看售后详情与进度"""
    return await get_after_sale_detail(db, after_sale_id, current_user.id)
