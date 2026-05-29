# 数据库构建文档

> 电商智能客服系统 — MySQL 8.0，数据库名 `ecommerce_cs`

---

## 一、环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| MySQL | 8.0+ | 字符集 utf8mb4 |
| Python | 3.9+ | pymysql 驱动 |

---

## 二、创建数据库

```sql
CREATE DATABASE IF NOT EXISTS ecommerce_cs
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

或者用命令行：

```bash
mysql -u root -e "CREATE DATABASE IF NOT EXISTS ecommerce_cs DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

---

## 三、表结构总览

共 8 张表，按业务领域分 4 组：

```
用户体系:       users
订单体系:       orders ──┬── order_items
                        └── logistics
售后体系:       after_sales
对话体系:       conversations ──┬── messages
                              └── transfer_logs
```

关系：

```
users (1) ──< (N) orders ──< (N) order_items
users (1) ──< (N) after_sales
orders (1) ── (1) logistics
users (1) ──< (N) conversations ──< (N) messages
conversations (1) ── (0..1) transfer_logs
```

---

## 四、表详细定义

### 4.1 users — 用户表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK AUTO_INCREMENT | 用户 ID |
| username | VARCHAR(50) | UNIQUE NOT NULL INDEX | 用户名 |
| password_hash | VARCHAR(255) | NOT NULL | pbkdf2_sha256 哈希 |
| phone | VARCHAR(20) | NULL | 手机号 |
| default_address | VARCHAR(255) | NULL | 默认收货地址 |
| created_at | DATETIME | NOT NULL DEFAULT NOW() | 注册时间 |
| updated_at | DATETIME | NOT NULL DEFAULT NOW() ON UPDATE NOW() | 更新时间 |

### 4.2 orders — 订单表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK AUTO_INCREMENT | 订单 ID |
| user_id | BIGINT | FK → users.id, NOT NULL INDEX | 所属用户 |
| order_no | VARCHAR(64) | UNIQUE NOT NULL INDEX | 订单编号 |
| status | VARCHAR(20) | DEFAULT 'pending' | pending/paid/shipped/delivered/cancelled |
| total_amount | DECIMAL(10,2) | NOT NULL | 订单金额 |
| shipping_address | VARCHAR(255) | NULL | 收货地址（下单时快照） |
| created_at | DATETIME | NOT NULL DEFAULT NOW() | 下单时间 |
| updated_at | DATETIME | NOT NULL DEFAULT NOW() ON UPDATE NOW() | 更新时间 |

### 4.3 order_items — 订单商品表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK AUTO_INCREMENT | |
| order_id | BIGINT | FK → orders.id, NOT NULL INDEX | 所属订单 |
| product_name | VARCHAR(200) | NOT NULL | 商品名称 |
| quantity | INT | NOT NULL | 数量 |
| price | DECIMAL(10,2) | NOT NULL | 单价 |

### 4.4 logistics — 物流表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK AUTO_INCREMENT | |
| order_id | BIGINT | FK → orders.id, NOT NULL INDEX | 所属订单 |
| company | VARCHAR(50) | NULL | 快递公司 |
| tracking_no | VARCHAR(100) | NULL | 快递单号 |
| status | VARCHAR(50) | DEFAULT 'pending' | 物流状态 |
| updated_at | DATETIME | NOT NULL DEFAULT NOW() ON UPDATE NOW() | 最新更新时间 |

### 4.5 after_sales — 售后表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK AUTO_INCREMENT | |
| order_id | BIGINT | FK → orders.id, NOT NULL INDEX | 关联订单 |
| user_id | BIGINT | FK → users.id, NOT NULL INDEX | 用户 ID |
| type | VARCHAR(20) | NOT NULL | return/refund/exchange |
| reason | TEXT | NOT NULL | 售后原因 |
| status | VARCHAR(20) | DEFAULT 'pending' | pending/approved/rejected/completed |
| created_at | DATETIME | NOT NULL DEFAULT NOW() | 申请时间 |
| updated_at | DATETIME | NOT NULL DEFAULT NOW() ON UPDATE NOW() | 更新时间 |

### 4.6 conversations — 对话会话表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK AUTO_INCREMENT | |
| user_id | BIGINT | FK → users.id, NOT NULL INDEX | 用户 ID |
| status | VARCHAR(20) | DEFAULT 'active' | active/transferred/closed |
| created_at | DATETIME | NOT NULL DEFAULT NOW() | 开始时间 |
| updated_at | DATETIME | NOT NULL DEFAULT NOW() ON UPDATE NOW() | 最后活动时间 |

### 4.7 messages — 对话消息表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK AUTO_INCREMENT | |
| conversation_id | BIGINT | FK → conversations.id, NOT NULL INDEX | 所属会话 |
| role | VARCHAR(20) | NOT NULL | user/agent/system |
| content | TEXT | NOT NULL | 消息内容 |
| created_at | DATETIME | NOT NULL DEFAULT NOW() | 发送时间 |

### 4.8 transfer_logs — 转人工记录表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK AUTO_INCREMENT | |
| conversation_id | BIGINT | FK → conversations.id, NOT NULL INDEX | 会话 ID |
| user_id | BIGINT | FK → users.id, NOT NULL INDEX | 用户 ID |
| reason | TEXT | NOT NULL | 转人工原因 |
| status | VARCHAR(20) | DEFAULT 'pending' | pending/processing/resolved |
| created_at | DATETIME | NOT NULL DEFAULT NOW() | 转接时间 |

---

## 五、建表方式

### 方式一：自动建表（开发阶段）

启动 `main.py` 时自动执行：

```python
# app/main.py
Base.metadata.create_all(bind=engine)
```

前提是数据库 `ecommerce_cs` 已存在。

### 方式二：独立建表脚本

```bash
python3 -c "from app.database import engine, Base; Base.metadata.create_all(engine)"
```

### 方式三：种子数据

```bash
python3 seed_data.py
```

会插入：1 个测试用户 + 4 条各状态订单 + 1 条售后记录。

---

## 六、测试账号

| 用户名 | 密码 | 说明 |
|--------|------|------|
| buyer1 | 123456 | 种子数据创建的买家，有 4 个订单和 1 个售后 |

---

## 七、状态机约定

### 订单状态流转

```
pending  →  paid  →  shipped  →  delivered
  ↓         ↓
cancelled  cancelled
```

- `pending` / `paid` 状态允许取消
- `shipped` / `delivered` 状态不允许取消
- 允许申请售后的状态：`paid` / `shipped` / `delivered`

### 售后状态流转

```
pending  →  approved  →  completed
         ↘  rejected
```

### 对话会话状态

```
active  →  transferred  →  closed
        ↘  closed
```

---

## 八、注意事项

1. `password_hash` 使用 `pbkdf2_sha256` 算法，不是 bcrypt
2. `order_items` 和 `logistics` 通过 `order_id` 关联订单，没有独立的用户外键（防止越权访问）
3. 所有时间字段由数据库自动填充（`DEFAULT NOW()`），不要手动设值
4. `shipping_address` 在创建订单时从用户地址快照，后续用户改地址不影响已有订单
