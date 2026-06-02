# Reasonix 开发工作流

本项目使用 Reasonix 的 Skill 系统驱动标准开发流程。

## 标准流程（任何编码任务）

```
1. brainstorming     → 需求分析 + 方案对比
2. writing-plans     → 编写实现计划（submit_plan）
3. implementation    → 按计划逐步实现
4. test-driven-dev   → 卷曲验证每个接口
5. code-review       → review skill 检查变更
```

## 可用的自定义 Skills

| Skill | 用途 | 类型 |
|------|------|------|
| `brainstorming` | 实现新功能前的需求分析和技术方案头脑风暴 | subagent |
| `writing-plans` | 编码前编写实现计划，列出修改文件和步骤 | subagent |
| `systematic-debugging` | 系统化调试：收集错误信息 → 定位根因 → 验证修复 | subagent |
| `test-driven-development` | TDD 工作流：先写测试 → 再写实现 → 验证通过 | subagent |
| `subagent-driven-development` | 将独立任务委派给子 Agent，并行执行后合并结果 | subagent |
| `start-dev` | 一键启动前后端 | inline |
| `api-test` | API 冒烟测试 | inline |
| `lint` | Python 语法检查 | subagent |

## 编码原则

1. 架构合理性 — 分层清晰，依赖方向单向
2. 关键步骤注释 — 解释"为什么这样写"
3. 不重复造轮子 — DRY 原则
4. 低耦合高内聚 — 每层只关心自己的事
5. Python 3.9 兼容 — 不用 `str | None`，用 `Optional[str]`

## 项目技术栈

- 后端：FastAPI + SQLAlchemy 2.0 async + MySQL
- 前端：React + Vite
- Agent：LangChain / LangGraph（Phase 3）
- 错误码：app/errors.py 统一管理
