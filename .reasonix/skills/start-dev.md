---
name: start-dev
description: 一键启动后端 (uvicorn) + 前端 (vite)，自动检查端口占用
---
## start-dev — 一键启动开发环境

启动后端 (FastAPI on :8000) 和前端 (Vite on :5173)。

### 操作步骤

1. 检查后端端口 8000 是否被占用，如果被占用则跳过启动
2. 用 `run_background` 启动后端: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. 检查前端端口 5173 是否被占用，如果被占用则跳过启动
4. 用 `run_background` 启动前端: `npx vite --host 0.0.0.0 --port 5173` (cwd: frontend)
5. 报告启动结果：后端地址 + 前端地址

### 注意事项

- 后端不要加 `--reload`（已知 greenlet 子进程问题）
- 如果端口已被占用且是同一服务的进程，说明已经在跑，不用重复启动
