# 电商智能客服系统 -- 项目文档 v0.3

> 个人学习项目，以实践驱动掌握 Python Web 开发 + AI Agent 开发
> 仓库：https://github.com/yyyz0211/ecommerce-cs

---

## 一、项目概述

### 1.1 目标

构建一个电商场景下的智能客服系统，用户可以通过对话方式查询订单、申请售后、跟进进度。后端由 FastAPI 提供 API，Agent 层使用 LangChain/LangGraph 处理对话逻辑，数据库使用 MySQL。

### 1.2 定位

- 个人学习作品，不以商用/上线为目标
- 先聚焦后端 API，后续再决定前端方案（前后端分离）
- 逐步迭代，先做核心链路，再扩展功能

### 1.3 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI | Python async Web 框架 |
| 数据库 | MySQL | 关系型数据库 |
| ORM | SQLAlchemy 2.0 async | 异步 ORM（aiomysql + greenlet） |
| Agent 框架 | LangChain / LangGraph | 构建对话智能体 |
| AI 模型 | OpenAI API / 国产大模型 API | 根据实际情况选择 |
| 前端 | 待定（Vue / React） | 后期决定 |
| 部署 | 无（本地开发调试） | |

### 1.4 学习路线（推荐顺序）

```
Python 基础语法 + 协程
      ↓
FastAPI 入门（路由、请求/响应模型）
      ↓
SQLAlchemy + MySQL（ORM、建表、查询）
      ↓
用户模块 API（注册、登录、鉴权）
      ↓
订单 + 售后模块 API（核心业务）
      ↓
Agent 基础（LangChain 对话链路）
      ↓
Agent + API 打通（agent 调用后端接口）
      ↓
多轮对话 + 转人工占位
      ↓
前端 / 卖家端 / 管理员端（后续迭代）
```

---

## 二、系统架构

### 2.1 整体架构（初期）

```
[用户] → [FastAPI REST API] → [MySQL]
                     ↓
              [Agent Service]
              (LangChain/LangGraph)
                     ↓
              [LLM API (OpenAI 等)]
```

### 2.2 目录结构（当前）

```
ecommerce-cs/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口
│   ├── config.py             # 配置（数据库、JWT、LLM）
│   ├── database.py           # 数据库连接 + 会话管理
│   ├── errors.py             # 统一错误码（11 个错误码）
│   ├── models/               # SQLAlchemy 模型（8 个类 → 8 张表）
│   │   ├── __init__.py
│   │   ├── base.py           # 模型基类（独立于 engine，避免循环导入）
│   │   ├── user.py
│   │   ├── order.py          # Order + OrderItem + Logistics
│   │   ├── after_sale.py
│   │   └── conversation.py   # Conversation + Message + TransferLog
│   ├── schemas/              # Pydantic 请求/响应模型
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── order.py
│   │   ├── after_sale.py
│   │   └── chat.py
│   ├── routers/              # API 路由（14 个端点）
│   │   ├── __init__.py
│   │   ├── auth.py           # 注册/登录/刷新
│   │   ├── users.py          # 个人信息 CRUD
│   │   ├── orders.py         # 订单 CRUD + 分页 + 取消
│   │   ├── after_sale.py     # 售后 CRUD
│   │   └── chat.py           # 会话管理（Phase 3 接 Agent）
│   ├── services/             # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── auth_service.py   # JWT 签发 + 鉴权注入
│   │   ├── user_service.py   # 注册/登录/修改
│   │   ├── order_service.py  # 订单查询/创建/取消 + 分页 + 状态校验
│   │   ├── after_sale_service.py
│   │   └── chat_service.py   # 会话 + 消息管理
│   └── agent/                # Agent 层（Phase 3）
│       └── __init__.py
├── tests/
├── debug.html                # 前端调试面板
├── seed_data.py              # 种子数据脚本
├── requirements.txt
├── .env.example
├── .gitignore
└── PROJECT.md
```

---

## 三、角色与权限（初期 -- 用户端）

### 3.1 角色

| 角色 | 本期做？ | 说明 |
|------|---------|------|
| 用户 | 做 | 电商买家，使用客服服务 |
| 卖家 | 暂不做 | 后续迭代 |
| 管理员 | 暂不做 | 后续迭代 |

### 3.2 用户端功能范围

| 功能模块 | 场景 | 优先级 |
|---------|------|--------|
| 用户注册/登录 | JWT 鉴权 | P0 |
| 订单查询 | 查订单状态、物流信息 | P0 |
| 退换货申请 | 提交售后申请 | P0 |
| 售后进度查询 | 查看售后处理状态 | P0 |
| 多轮对话 Agent | 自然语言对话完成上述操作 | P0 |
| 模拟转人工 | Agent 判定后"转接"并记录到数据库 | P1 |
| 对话历史 | 查看历史对话记录 | P2 |

---

## 四、API 接口设计（初版）

### 4.1 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/register | 注册 |
| POST | /api/auth/login | 登录，返回 JWT |
| POST | /api/auth/refresh | 刷新 Token |

### 4.2 用户

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/users/me | 获取当前用户信息 |
| PATCH | /api/users/me | 修改个人信息（地址等） |

### 4.3 订单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/orders?page=1&size=10 | 获取我的订单列表（分页） |
| POST | /api/orders | 创建订单（调试用） |
| GET | /api/orders/{id} | 获取订单详情（含商品明细） |
| PATCH | /api/orders/{id}/cancel | 取消订单（pending/paid 可取消） |
| GET | /api/orders/{id}/logistics | 获取物流信息 |

### 4.4 售后

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/after-sales | 提交售后申请 |
| GET | /api/after-sales | 查看我的售后列表 |
| GET | /api/after-sales/{id} | 查看售后详情与进度 |

### 4.5 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/chat/session | 创建新对话会话 |
| POST | /api/chat/message | 发送消息，Agent 回复（Phase 3） |
| GET | /api/chat/history/{session_id} | 获取某次对话记录 |

`POST /api/chat/message` 是核心接口，大致流程：

```
用户消息 → FastAPI → Agent Service(LangGraph)
                         ↓
               Agent 判断意图（查订单/售后/转人工等）
                         ↓
               Agent 调用对应 Tool（查询 API / 操作 API）
                         ↓
               Agent 生成自然语言回复
                         ↓
               返回给用户 + 记录到数据库
```

### 4.6 错误格式

所有错误统一返回 `{"code": "...", "message": "..."}`，不单独散落 `detail`：

| code | HTTP 状态码 | 说明 |
|------|-----------|------|
| INVALID_TOKEN | 401 | JWT 无效 |
| USER_NOT_FOUND | 401 | 用户不存在 |
| WRONG_PASSWORD | 401 | 密码错误 |
| USERNAME_TAKEN | 409 | 用户名已存在 |
| ORDER_NOT_FOUND | 404 | 订单不存在 |
| ORDER_CANNOT_CANCEL | 400 | 订单不可取消（动态 message） |
| LOGISTICS_NOT_FOUND | 404 | 暂无物流信息 |
| AFTER_SALE_NOT_FOUND | 404 | 售后记录不存在 |
| CONVERSATION_NOT_FOUND | 404 | 会话不存在 |

定义位置：`app/errors.py`，全局处理器在 `app/main.py`。

---

## 五、对话设计（Agent 部分）

### 5.1 Agent 能力范围

初期 agent 能做的事情：

- 识别用户意图（查订单 / 申请售后 / 查售后进度 / 转人工 / 闲聊）
- 调用后端 API 获取订单数据
- 调用后端 API 提交售后申请
- 在上下文中维护多轮对话
- 在敏感操作（涉及退款等）时提示转人工
- 模拟"已转接人工客服"，记录转接事件到数据库

### 5.2 半自动模式规则

| 操作 | Agent 处理 | 需转人工 |
|------|-----------|---------|
| 查订单状态 | 直接查询返回 | 否 |
| 查物流信息 | 直接查询返回 | 否 |
| 查售后进度 | 直接查询返回 | 否 |
| 提交退换货申请 | 收集信息后提交 | 提交后告知已转人工审核 |
| 涉及退款金额 | 不处理，转人工 | 是 |
| 用户要求找人工 | 转人工 | 是 |

### 5.3 转人工机制（初版占位）

```
用户要求转人工 / agent 判定需转人工
         ↓
Agent 回复"已转接人工客服，请稍候，会尽快为您处理"
         ↓
后端记录一条转人工记录到 transfer_log 表
（标记为待处理，无真人处理，仅日志记录）
         ↓
对话会话标记为"已转人工"状态
```

---

## 六、数据库表设计（初版）

### 6.1 用户表 (users)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 用户 ID |
| username | VARCHAR(50) UNIQUE | 用户名 |
| password_hash | VARCHAR(255) | 密码哈希 |
| phone | VARCHAR(20) | 手机号 |
| default_address | TEXT | 默认收货地址 |
| created_at | DATETIME | 注册时间 |
| updated_at | DATETIME | 更新时间 |

### 6.2 订单表 (orders)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 订单 ID |
| user_id | BIGINT FK | 用户 ID |
| order_no | VARCHAR(64) UNIQUE | 订单编号 |
| status | VARCHAR(20) | 状态（pending/paid/shipped/delivered/cancelled） |
| total_amount | DECIMAL(10,2) | 订单金额 |
| created_at | DATETIME | 下单时间 |
| updated_at | DATETIME | 更新时间 |

### 6.3 订单商品表 (order_items)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | |
| order_id | BIGINT FK | 订单 ID |
| product_name | VARCHAR(200) | 商品名称 |
| quantity | INT | 数量 |
| price | DECIMAL(10,2) | 单价 |

### 6.4 物流表 (logistics)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | |
| order_id | BIGINT FK | 订单 ID |
| company | VARCHAR(50) | 快递公司 |
| tracking_no | VARCHAR(100) | 快递单号 |
| status | VARCHAR(50) | 物流状态 |
| updated_at | DATETIME | 最新更新时间 |

### 6.5 售后表 (after_sales)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | |
| order_id | BIGINT FK | 关联订单 |
| user_id | BIGINT FK | 用户 ID |
| type | VARCHAR(20) | 类型（return/refund/exchange） |
| reason | TEXT | 售后原因 |
| status | VARCHAR(20) | 状态（pending/approved/rejected/completed） |
| created_at | DATETIME | 申请时间 |
| updated_at | DATETIME | 更新时间 |

### 6.6 对话会话表 (conversations)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | |
| user_id | BIGINT FK | 用户 ID |
| status | VARCHAR(20) | 状态（active/transferred/closed） |
| created_at | DATETIME | 开始时间 |
| updated_at | DATETIME | 最后活动时间 |

### 6.7 对话消息表 (messages)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | |
| conversation_id | BIGINT FK | 会话 ID |
| role | VARCHAR(20) | user / agent / system |
| content | TEXT | 消息内容 |
| created_at | DATETIME | 发送时间 |

### 6.8 转人工记录表 (transfer_logs)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | |
| conversation_id | BIGINT FK | 会话 ID |
| user_id | BIGINT FK | 用户 ID |
| reason | TEXT | 转人工原因 |
| status | VARCHAR(20) | 状态（pending/processing/resolved） |
| created_at | DATETIME | 转接时间 |

---

## 七、开发阶段规划

### Phase 1：项目骨架 [已完成]
- [x] 初始化 FastAPI 项目
- [x] 配置 MySQL 连接 + SQLAlchemy
- [x] 实现用户注册/登录（JWT）
- [x] 验证接口可用

### Phase 2：业务 API [已完成]
- [x] 订单表 + API（查询列表、详情）
- [x] 物流表 + API
- [x] 售后表 + API（提交申请、查询进度）
- [x] 编写测试数据（种子数据）

### Phase 2.5：补全接口 + 优化 [已完成]
- [x] POST /api/auth/refresh（刷新 Token）
- [x] PATCH /api/users/me（修改个人信息）
- [x] POST /api/orders（创建测试订单）
- [x] PATCH /api/orders/{id}/cancel（取消订单 + 状态校验）
- [x] 订单列表分页（?page=&size=）
- [x] 对话会话基础设施（POST session / GET history）
- [x] 前端调试面板（debug.html）
- [x] SQLAlchemy 异步迁移（async engine + AsyncSession + select() 语法）
- [x] 统一错误码（app/errors.py，11 个 AppError + 全局异常处理器）

### Phase 3：Agent 对话 ← 当前
- [ ] 接入 LLM API（配置 Key，测试调用）
- [ ] LangChain 基础对话链路
- [ ] 自定义 Tool：查订单
- [ ] 自定义 Tool：查物流
- [ ] 自定义 Tool：提交售后申请
- [ ] LangGraph 多轮对话编排
- [ ] 意图识别 + 工具调用
- [ ] task_state 结构设计
- [ ] next_action 规则表 + LLM 可选覆盖策略

### Phase 4：对话 API + 完善
- [ ] 转人工占位机制
- [ ] Agent 回复流接入 POST /api/chat/message
- [ ] 对话记录入库（Agent 消息）
- [ ] 边界情况处理（意图不明确、API 调用失败等）

---

## Phase 3.5：task_state 结构设计

### 设计目标

`task_state` 用于在多轮对话中记录**当前任务的流程状态**，让 Agent 能够：

- 知道对话进行到哪一步
- 判断下一步应该做什么
- 在上下文压缩后仍能恢复关键业务参数（订单号、售后类型等）

### 推荐结构

```json
{
  "version": 1,
  "stage": "awaiting_order_id",
  "intent": "query_logistics",
  "status": "in_progress",
  "order_id": null,
  "customer_id": null,
  "confidence": 0.92,
  "next_action": "ask_user_for_order_id",
  "updated_at": "2026-06-03T14:52:00+08:00"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | int | Schema 版本号，方便后续升级兼容 |
| `stage` | str | 当前对话阶段（见下方枚举） |
| `intent` | str | 识别到的用户意图（见下方枚举） |
| `status` | str | 任务整体状态（见下方枚举） |
| `order_id` | int/null | 业务关键字段：当前关联的订单 ID |
| `customer_id` | int/null | 用户 ID（可省略，与 user_id 重复） |
| `confidence` | float | 综合置信度，0.0 ~ 1.0 |
| `next_action` | str | 下一步系统应该做什么（见下方枚举） |
| `updated_at` | str | ISO 8601 时间戳 |

### 推荐枚举值

#### `stage`（对话阶段）

| 值 | 说明 |
|---|---|
| `new` | 新对话，未开始任务 |
| `awaiting_order_id` | 等待用户提供订单号 |
| `awaiting_confirmation` | 等待用户确认信息 |
| `processing` | 正在处理（调用 API 中） |
| `completed` | 任务已完成 |
| `failed` | 任务失败 |

#### `intent`（用户意图）

| 值 | 说明 |
|---|---|
| `query_order_status` | 查询订单状态 |
| `query_logistics` | 查询物流信息 |
| `query_after_sale` | 查询售后进度 |
| `submit_after_sale` | 提交售后申请 |
| `cancel_order` | 取消订单 |
| `transfer_human` | 转人工 |
| `other` | 其他/未识别 |

#### `status`（任务状态）

| 值 | 说明 |
|---|---|
| `pending` | 待处理 |
| `in_progress` | 进行中 |
| `done` | 已完成 |
| `error` | 异常/失败 |

#### `next_action`（下一步动作）

| 值 | 说明 |
|---|---|
| `ask_user_for_order_id` | 让用户提供订单号 |
| `confirm_user_intent` | 确认用户意图 |
| `call_backend_api` | 调用后端 API |
| `reply_user` | 回复用户 |
| `transfer_to_human` | 转人工 |
| `stop` | 结束对话 |

### confidence 设计原则

`confidence` 是一个**综合置信度**，建议由模型分数、规则命中、上下文完整度共同决定。

#### 计算策略

```
final_confidence = 模型概率 × 0.4 + 规则命中 × 0.3 + 上下文完整度 × 0.3
```

#### 使用建议

| confidence 范围 | 系统行为 |
|----------------|----------|
| >= 0.85 | 可直接执行，无需确认 |
| 0.6 ~ 0.85 | 先确认，再执行 |
| < 0.6 | 走兜底逻辑或转人工 |

> **注**：如果你的意图种类少、业务流程简单，可以先不加 `confidence`，关键分支靠 `stage` / `intent` / `tool_calls` 足够支撑。

### 落地到代码

`task_state` 当前存在：

1. **conversation_memories 表**：`memory_type = "task_state"`，`content` 存 JSON 字符串
2. **唯一性边界**：同一会话同一 `memory_type` 只保留一条，使用 `conversation_id + memory_type` 约束
3. **保存时机**：
   - Agent 每次回复后更新
   - 关键节点（拿到 order_id、提交售后成功等）
4. **读取时机**：
   - Agent 每次处理消息时从 DB 加载
   - 用于恢复上下文、决定下一步

#### 示例存储格式

```python
task_state = {
    "version": 1,
    "stage": "completed",
    "intent": "query_logistics",
    "status": "done",
    "order_id": 12345,
    "confidence": 0.95,
    "next_action": "reply_user",
    "updated_at": "2026-06-03T14:52:00+08:00"
}
```

#### 与现有代码的衔接

当前实现已将 `task_state` 接入 LangGraph 返回值：

- `graph._build_task_state()` 根据工具调用和工具结果生成结构化状态
- `chat_service.process_agent_message()` 从 graph 结果读取状态
- `memory_service.save_task_state()` 统一序列化并落库
- `graph._format_memory_for_prompt()` 按 `summary / task_state / preference / fact` 分层注入系统提示词

### Phase 4.5：RAG 知识库

#### 步骤 4.5.1：数据爬取（京东帮助中心）
- [ ] 分析京东帮助中心页面结构（help.jd.com）
- [ ] 编写爬虫脚本 `scripts/crawl_jd_faq.py`
  - 目标分类：售后政策、物流配送、支付发票、账户管理
  - 每类约 50 条，总计约 200 条 FAQ
  - 处理 GBK 编码
- [ ] 编写清洗脚本 `scripts/clean_faq.py`
  - HTML → 纯文本
  - LLM 辅助提取 Q&A 对
  - 输出为 `knowledge/` 目录下的 Markdown 文件

#### 步骤 4.5.2：知识库搭建
- [ ] 向量数据库搭建（Chroma，本地轻量）
- [ ] 文档切片策略测试（固定长度 vs 语义分块）
- [ ] Embedding（OpenAI embedding 或本地模型）
- [ ] 召回精度测试（评估不同切片策略的效果）

#### 步骤 4.5.3：Agent 集成
- [ ] Agent Tool: search_knowledge_base（向量检索）
- [ ] Prompt 模板：检索结果 + 用户问题 → LLM 生成回答
- [ ] 边界测试：知识库没有的问题（不应强行编造）

### Phase 5：测试 + 优化
- [ ] 单元测试（关键业务逻辑）
- [ ] 手动测试完整对话链路
- [ ] 补全文档和注释
- [ ] 前端框架（Vue/React）替换 debug.html

---

## 八、学习建议

### 8.1 每阶段的学习方法

1. **先读再写**：每个新组件（FastAPI、SQLAlchemy、LangChain）先看官方文档的 Quickstart 跑通最小示例
2. **写一小步就跑一次**：不要一口气写完一个模块再测试，每加一个路由就 curl 验证
3. **用种子数据**：预先在 MySQL 里插入测试订单/商品数据，方便调试时不用每次手动操作
4. **错误是学习的一部分**：FastAPI 的错误提示通常很清晰，读懂了就是进步

### 8.2 遇到问题时的排查顺序

```
1. 看 FastAPI 终端报错信息（最直接）
2. 检查 .env 配置（数据库地址、API Key 是否写对）
3. 确认 MySQL 服务是否在运行
4. 搜索：记下完整的报错信息去搜
5. 问我：把报错信息贴给我看
```

---

## 九、未尽事项（后续迭代再定）

- 卖家端系统设计
- 管理员后台（知识库、对话管理）
- 前端框架选型（React / Vue）
- 部署方案
- RAG 知识库（Phase 4.5）
- 对话数据分析和统计
- 多模型切换
- 语音/多模态

---

## 十、附录

### 10.1 依赖清单

```
# 核心
fastapi
uvicorn[standard]
sqlalchemy>=2.0
pymysql
alembic
pydantic
pydantic-settings
python-dotenv

# 认证
python-jose[cryptography]
passlib[bcrypt]

# Agent
langchain
langgraph
openai
httpx

# RAG（Phase 4.5）
chromadb
langchain-text-splitters

# 测试
pytest
```

---

> 文档版本：v0.4
> 最后更新：2026-06-03
> 下一步：Phase 3 Agent 对话 → task_state 结构设计（已完成）
