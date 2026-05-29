"""应用配置 -- 从环境变量 / .env 文件加载"""

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- 数据库 ---
    DATABASE_URL: str = "mysql+pymysql://root:root@localhost:3306/ecommerce_cs"

    # --- JWT ---
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- LLM（Phase 3 启用） ---
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "gpt-4o-mini"

    class Config:
        env_file = ".env"


settings = Settings()
