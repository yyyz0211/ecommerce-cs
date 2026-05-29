"""用户服务：注册、登录、修改个人信息"""

from typing import Optional

from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.auth_service import create_access_token

# 密码加密上下文（使用 pbkdf2_sha256，不依赖外部 bcrypt 库）
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def register_user(
    db: Session, username: str, password: str, phone: Optional[str] = None
) -> User:
    """注册新用户 -- 用户名唯一校验后写入数据库"""
    # 数据清洗：去除首尾空格，防止 "alice" 和 " alice " 被视为两个用户
    username = username.strip()
    phone = phone.strip() if phone else None

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    user = User(
        username=username,
        password_hash=hash_password(password),
        phone=phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, username: str, password: str) -> str:
    """登录验证 -- 校验密码并返回 JWT 令牌"""
    username = username.strip()
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return create_access_token(user.id)


def update_user(
    db: Session, user: User, phone: Optional[str] = None, default_address: Optional[str] = None
) -> User:
    """修改当前用户信息 -- 只更新传入的字段，未传入的保持不变"""
    if phone is not None:
        user.phone = phone.strip() if phone else None
    if default_address is not None:
        user.default_address = default_address.strip() if default_address else None
    db.commit()
    db.refresh(user)
    return user
