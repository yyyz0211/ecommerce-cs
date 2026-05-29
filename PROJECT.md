# 电商智能客服系统 -- 项目文档 v0.1

> 个人学习项目，以实践驱动掌握 Python Web 开发 + AI Agent 开发

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
| ORM | SQLAlchemy 2.0 + Alembic | 数据库操作与迁移 |
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

### 2.2 目录结构（初期规划）

```
ecommerce-cs/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口
│   ├── config.py             # 配置（数据库、API Key 等）
│   ├── database.py           # 数据库连接
│   ├── models/               # SQLAlchemy 模型
│   │   ├── __init__.py
│   │   ├── user.py           # 用户模型
│   │   ├── order.py          # 订单模型
│   │   └── conversation.py   # 对话记录模型
│   ├── schemas/              # Pydantic 请求/响应模型
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── order.py
│   │   └── chat.py
│   ├── routers/              # API 路由
│   │   ├── __init__.py
│   │   ├── auth.py           # 认证
│   │   ├── users.py          # 用户信息
│   │   ├── orders.py         # 订单查询
│   │   ├── after_sale.py     # 售后处理
│   │   └── chat.py           # 对话入口
│   ├── services/             # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── order_service.py
│   │   ├── after_sale_service.py
│   │   └── agent_service.py  # Agent 对话逻辑
│   └── agent/                # Agent 层
│       ├── __init__.py
│       ├── llm.py            # LLM 客户端配置
│       ├── tools.py          # 自定义工具（查订单、提交售后等）
│       └── graph.py          # LangGraph 对话图定义
├── alembic/                  # 数据库迁移
├── tests/                    # 测试
├── requirements.txt
├── .env                       # 环境变量（不提交）
└── PROJECT.md                # 本文档
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
| GET | /api/orders | 获取我的订单列表 |
| GET | /api/orders/{id} | 获取订单详情 |
| GET | /api/orders/{id}/logistics | 获取物流信息 |

### 4.4 售后

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/after-sales | 提交售后申请 |
| GET | /api/after-sales | 查看我的售后列表 |
| GET | /api/after-sales/{id} | 查看售后详情与进度 |

### 4.5 对话（核心）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/chat/session | 创建新对话会话 |
| POST | /api/chat/message | 发送消息，Agent 回复 |
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

### Phase 1：项目骨架
- [ ] 初始化 FastAPI 项目
- [ ] 配置 MySQL 连接 + SQLAlchemy
- [ ] 配置 Alembic 迁移
- [ ] 实现用户注册/登录（JWT）
- [ ] 验证接口可用

### Phase 2：业务 API
- [ ] 订单表 + API（查询列表、详情）
- [ ] 物流表 + API
- [ ] 售后表 + API（提交申请、查询进度）
- [ ] 编写测试数据（种子数据）

### Phase 3：Agent 对话
- [ ] 接入 LLM API（配置 Key，测试调用）
- [ ] LangChain 基础对话链路
- [ ] 自定义 Tool：查订单
- [ ] 自定义 Tool：查物流
- [ ] 自定义 Tool：提交售后申请
- [ ] LangGraph 多轮对话编排
- [ ] 意图识别 + 工具调用

### Phase 4：对话 API + 完善
- [ ] 对话会话管理（创建/查询历史）
- [ ] Agent 回复流接入 POST /api/chat/message
- [ ] 转人工占位机制
- [ ] 对话记录入库
- [ ] 边界情况处理（意图不明确、API 调用失败等）

### Phase 5：测试 + 优化
- [ ] 单元测试（关键业务逻辑）
- [ ] 手动测试完整对话链路
- [ ] 补全文档和注释
- [ ] （可选）简单前端页面联调

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
- 知识库（FAQ）管理
- 对话数据分析和统计
- 多模型切换
- 语音/多模态

---

## 十、附录

### 10.1 依赖清单（初版）

```
fastapi
uvicorn[standard]
sqlalchemy>=2.0
pymysql
alembic
python-dotenv
python-jose[cryptography]  # JWT
passlib[bcrypt]             # 密码哈希
pydantic
httpx                       # Agent 调用外部 API 使用
langchain
langgraph
openai                      # 或其他 LLM SDK
pytest
httpx                       # 测试用
```

---

> 文档版本：v0.1
> 最后更新：2026-05-28
> 下一步：确认文档内容无误后，进入 Phase 1 开发
