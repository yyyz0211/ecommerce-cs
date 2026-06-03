"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.errors import AppError
from app.logger import configure_agent_only_logging

from app.models.base import Base
from app.database import engine
from app.routers import auth, users, orders, after_sale, chat

configure_agent_only_logging()

async def init_db():
    """异步建表 -- 用 run_sync 在事件循环中执行同步 DDL"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="电商智能客服系统", version="0.1.0", lifespan=lifespan)


# ── 统一错误处理 ──

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """统一将 AppError 转为 JSON 响应"""
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """兜底捕获未预期的异常"""
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "服务器内部错误"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(orders.router)
app.include_router(after_sale.router)
app.include_router(chat.router)

@app.get("/")
def root():
    return {"message": "电商智能客服系统 API 已启动"}
