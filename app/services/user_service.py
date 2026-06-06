"""用户服务：注册、登录、修改个人信息"""

from typing import Optional

from app.errors import USERNAME_TAKEN, WRONG_PASSWORD
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth_service import create_access_token

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


async def register_user(
    db: AsyncSession, username: str, password: str, phone: Optional[str] = None
) -> User:
    """注册新用户 -- 用户名唯一校验后写入数据库"""
    username = username.strip()
    phone = phone.strip() if phone else None

    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == username))
    existing = result.scalar_one_or_none()
    if existing:
        raise USERNAME_TAKEN

    user = User(
        username=username,
        password_hash=hash_password(password),
        phone=phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, username: str, password: str) -> str:
    """登录验证 -- 校验密码并返回 JWT 令牌"""
    username = username.strip()
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise WRONG_PASSWORD
    return create_access_token(user.id)


async def update_user(
    db: AsyncSession,
    user: User,
    phone: Optional[str] = None,
    default_address: Optional[str] = None,
) -> User:
    """修改当前用户信息 -- 只更新传入的字段，未传入的保持不变"""
    if phone is not None:
        user.phone = phone.strip() if phone else None
    if default_address is not None:
        user.default_address = default_address.strip() if default_address else None
    await db.commit()
    await db.refresh(user)
    return user
