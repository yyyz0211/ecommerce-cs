"""用户信息路由：查看/修改个人信息"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserInfoResponse, UserUpdateRequest
from app.services.auth_service import get_current_user
from app.services.user_service import update_user

router = APIRouter(prefix="/api/users", tags=["用户"])


@router.get("/me", response_model=UserInfoResponse)
async def get_my_info(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return await current_user


@router.patch("/me", response_model=UserInfoResponse)
async def update_my_info(
    req: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前用户的手机号或收货地址"""
    return await update_user(db, current_user, phone=req.phone, default_address=req.default_address)
