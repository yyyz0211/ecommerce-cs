"""FastAPI 应用入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, users, orders, after_sale, chat

# 创建所有数据库表（开发阶段方便，后续改用 Alembic 迁移）
Base.metadata.create_all(bind=engine)

app = FastAPI(title="电商智能客服系统", version="0.1.0")

# 开发阶段允许跨域请求（前端调试用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 注册路由 ───
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(orders.router)
app.include_router(after_sale.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {"message": "电商智能客服系统 API 已启动"}
