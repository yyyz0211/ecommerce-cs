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

    # --- LLM ---
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # ── 摘要压缩专用配置（默认复用主链路，可单独配以隔离速率配额）──
    LLM_SUMMARY_MODEL: str = os.getenv("LLM_SUMMARY_MODEL", LLM_MODEL)
    LLM_SUMMARY_API_KEY: Optional[str] = os.getenv("LLM_SUMMARY_API_KEY", OPENAI_API_KEY)
    LLM_SUMMARY_BASE_URL: Optional[str] = os.getenv("LLM_SUMMARY_BASE_URL", OPENAI_BASE_URL)


settings = Settings()
