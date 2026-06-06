"""数据库引擎与会话管理 -- 异步版本"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.models.base import Base  # noqa: F401 — 确保模型注册

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    """FastAPI 依赖注入：获取异步数据库会话"""
    async with AsyncSessionLocal() as db:
        yield db
