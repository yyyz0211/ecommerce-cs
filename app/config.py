"""应用配置 -- 手动加载 .env，避免环境变量冲突"""

import os
from typing import Optional

from dotenv import load_dotenv

# 先加载 .env 文件（不 override 已有环境变量）
load_dotenv(".env", override=True)


class Settings:
    # --- 数据库 ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "mysql+aiomysql://root@localhost:3306/ecommerce_cs")

    # --- JWT ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # --- LLM（Phase 3 启用） ---
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")


settings = Settings()
