"""JWT 令牌工具：创建、校验、获取当前用户"""

from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.errors import INVALID_TOKEN, USER_NOT_FOUND
from app.models.user import User

bearer_scheme = HTTPBearer()

def create_access_token(user_id: int) -> str:
    """生成 JWT 访问令牌"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 JWT 令牌中解析出当前登录用户（FastAPI 依赖注入用）"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise INVALID_TOKEN

    user = await db.get(User, user_id)
    if not user:
        raise USER_NOT_FOUND
    return user
