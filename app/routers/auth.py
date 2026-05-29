"""认证路由：注册、登录、刷新令牌"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserRegisterRequest,
    UserRegisterResponse,
    UserLoginRequest,
    TokenResponse,
)
from app.services.auth_service import create_access_token, get_current_user
from app.services.user_service import register_user, login_user

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=UserRegisterResponse, status_code=201)
def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    user = register_user(db, username=req.username, password=req.password, phone=req.phone)
    return user


@router.post("/login", response_model=TokenResponse)
def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    """用户登录，返回 JWT 令牌"""
    token = login_user(db, username=req.username, password=req.password)
    return TokenResponse(access_token=token)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(current_user: User = Depends(get_current_user)):
    """用当前有效令牌换取新令牌，延长登录有效期"""
    new_token = create_access_token(current_user.id)
    return TokenResponse(access_token=new_token)
