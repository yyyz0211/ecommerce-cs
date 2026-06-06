#!/bin/bash
# 临时清除环境变量中的 DATABASE_URL，让 pydantic-settings 使用 .env 文件
unset DATABASE_URL
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
