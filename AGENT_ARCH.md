# LangGraph Agent 流程图

## 全局状态（State）

```python
class AgentState(TypedDict):
    messages: list[BaseMessage]   # 对话历史（user + assistant + tool）
    user_id: int                   # 当前用户 ID
    conversation_id: int           # 当前会话 ID
    memory: dict                   # 记忆（last_order_id, last_query_type 等）
```

这个 state 在图的每个节点之间传递，每个节点都可以读取和修改它。

---

## 图结构

```
                    START
                      │
                      ▼
              ┌───────────────┐
              │   load_memory  │  ← 从 DB 加载历史记忆到 state.memory
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │   call_llm     │  ← 调 LiteLLM，传入 messages + tools
              │                │    返回 message 追加到 state.messages
              └───────┬───────┘
                      │
              ┌───────▼───────┐
              │  should_continue │  ← 检查最新 message 有没有 tool_calls
              │  (条件判断)      │
              └───────┬───────┘
                      │
         ┌────────────┴────────────┐
         │ 有 tool_call            │ 没有 tool_call
         ▼                         ▼
  ┌──────────────┐          ┌──────────────┐
  │ execute_tool  │          │ save_memory   │  ← 保存当前交互到记忆
  │              │          └──────┬───────┘
  │ 根据工具名称   │               │
  │ 路由到对应函数 │               ▼
  │              │          ┌──────────────┐
  │ 查订单        │          │   END         │  ← 返回 state.messages
  │ 查物流        │          └──────────────┘
  │ 提交售后      │
  │ 转人工        │
  └──────┬───────┘
         │
         │ (回到 call_llm，带着工具结果)
         └─────────────────────→ call_llm
```

---

## 每个节点的具体逻辑

### 1. load_memory

```
输入: user_id, conversation_id
操作: 从 memory 表查上次交互的关键信息
      → { "last_order_id": 10, "last_query_type": "order_detail" }
输出: state.memory = {...}
```

作用：用户说"查物流"时，能从 memory 知道上次查的是哪个订单。

---

### 2. call_llm

```
输入: state.messages（含历史）+ state.memory + tools 定义

拼接后的消息列表：
  System: "你是电商客服...当前用户 ID 是 {state.user_id}"
  Human: "查一下我的第 2 个订单"   ← 用户最新消息
  (之前的历史消息)

调用:
  response = litellm.completion(
      model="gpt-4o-mini",
      messages=组成好的消息列表,
      tools=tools_definition,
  )

输出: state.messages.append(response.message)
```

LLM 返回的 response 有两种可能：

**情况 A** — 直接文字回复：
```
response.content = "您有 3 个订单..."
response.tool_calls = None
→ should_continue 判断：无 tool_call → 走 END
```

**情况 B** — 调工具：
```
response.content = None
response.tool_calls = [
  {
    "id": "call_xxx",
    "function": {
      "name": "query_orders",
      "arguments": '{"user_id": 6}'
    }
  }
]
→ should_continue 判断：有 tool_call → 走 execute_tool
```

---

### 3. should_continue（条件判断）

```python
def should_continue(state: AgentState) -> str:
    last_msg = state.messages[-1]
    if last_msg.tool_calls:
        return "execute_tool"   # 继续
    else:
        return "end"             # 结束
```

---

### 4. execute_tool

```
输入: state.messages[-1].tool_calls

循环处理每个 tool_call：

  tool_name = tool_call.function.name
  args = json.loads(tool_call.function.arguments)

  if tool_name == "query_orders":
      orders = await get_user_orders(db, user_id=args["user_id"])
      result = {
          "orders": [
              {
                  "order_id": order.id,
                  "status": order.status,
                  "amount": str(order.amount),
                  "currency": "CNY"
              }
              for order in orders
          ]
      }

  elif tool_name == "query_logistics":
      logistics = await get_order_logistics(db, ...)
      result = {
          "order_id": logistics.order_id,
          "status": logistics.status,
          "carrier": logistics.carrier,
          "tracking_no": logistics.tracking_no
      }

  elif tool_name == "submit_after_sale":
      record = await create_after_sale(db, ...)
      result = {
          "after_sale_id": record.id,
          "status": record.status
      }

  elif tool_name == "transfer_to_human":
      transfer_log = create_transfer_log(db, ...)
      conversation.status = "transferred"
      result = {
          "status": "transferred"
      }

  # 工具结果作为结构化 ToolMessage 追加到 state
  state.messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=tool_call.id))

输出: state.messages（多了 ToolMessage）
→ 返回 call_llm 节点，让 LLM 基于结构化结果生成回复
```

---

### 5. save_memory

`save_memory` 应在用户回复完成后异步执行，避免阻塞主对话链路。

#### 推荐流程

```
回复用户
↓
立即返回
↓
后台任务
↓
生成 summary
↓
更新 memory
```

#### 设计原则

- 用户回复优先返回，不能被记忆总结阻塞
- `save_memory` 作为异步后台任务执行
- 总结内容只在后台生成，不影响主对话链路
- 记忆更新失败不能影响本轮回复
- 记忆总结与用户回复解耦

#### `save_memory` 的职责

`save_memory` 只负责：

- 汇总本轮结果
- 生成新的 `summary`
- 必要时更新 `task_state / preference / fact`
- 持久化到 memory 存储

#### 不要做的事

- 不要在主回复路径里等待总结完成
- 不要让记忆更新阻塞用户响应
- 不要把工具原始输出直接写进 `summary`
- 不要让 `save_memory` 参与本轮回复生成

#### 读取与写入分离

- 主流程只读取已有记忆并生成回复
- 后台流程负责根据本轮对话异步更新记忆
- 读取和写入不要互相阻塞

### 概述

`memory` 是 Agent 的跨轮次上下文，分四种类型，每种有不同的用途、更新策略和触发条件。

---

### 类型总览

| `memory_type` | 用途 | 存什么 | 触发条件 | 更新策略 |
|---|---|---|---|---|
| `summary` | 给 LLM 看 的会话摘要 | 当前主题、目标、进展、下一步意图 | 主题切换、阶段完成、对话过长时压缩 | 覆盖写 |
| `task_state` | 给程序看的执行状态 | 当前对象 ID、当前流程状态、等待态、已执行动作 | 工具执行后、任务状态变化时 | 覆盖写 |
| `preference` | 用户长期偏好 | 表达风格、语言偏好、展示格式偏好等 | 明确识别到稳定偏好时 | 覆盖写 |
| `fact` | 稳定事实记忆 | 用户确认过且后续可复用的信息 | 事实被确认且后续可能复用 | 覆盖写或按 key 更新 |

---

### `summary` 设计原则

`summary` 只给 LLM 看，负责提供高层语义上下文，不承担程序状态存储职责。

`summary` 应该只保留：

- **主题**：用户最近在做什么
- **目标**：用户想完成什么
- **进展**：当前推进到了哪一步
- **下一步意图**：接下来应该继续什么方向

`summary` 不应该重复存放程序已经能直接读取的状态字段。

#### `summary` 的内容示例

- 用户最近在查询订单物流
- 物流查询已完成
- 当前没有待处理任务

#### `summary` 不要存的内容

- 订单号
- 物流单号
- 查询类型枚举值
- 是否等待确认这类程序状态
- 原始工具输出

`summary` 的目标是：**让 LLM 快速理解当前上下文，但不要把执行状态塞进去。**

#### `summary` 的正确形态

```
用户最近在查询订单物流。
物流已查询完成。
当前没有待处理任务。
```

风格要求：

- 短
- 稳定
- 面向未来
- 不包含过程噪声

---

### `task_state` 设计原则

`task_state` 只给程序看，负责保存可执行、可判断、可恢复的状态。

#### `task_state` 应该存的内容

```json
{
  "current_order_id": "202605280002",
  "current_logistics_no": "ZT9876543210",
  "current_query_type": "logistics",
  "awaiting_confirmation": false
}
```

这类字段是程序执行需要直接读取的状态：

- 当前处理的是哪个对象
- 当前处于什么流程阶段
- 是否还需要用户确认
- 当前动作是否完成

#### `task_state` 不要存的内容

- 对话摘要
- 自然语言总结
- 面向 LLM 的上下文描述
- 大段解释文字

`task_state` 的目标是：**程序可执行状态，不混入语义摘要。**

#### 更新策略

- 覆盖写
- 每次任务状态变化时更新
- 只保留当前有效状态，不保留历史流水

---

### 两者的分工原则

#### `summary`

- 面向 LLM
- 描述“发生了什么”
- 提供高层语义上下文

#### `task_state`

- 面向程序
- 描述“现在是什么状态”
- 提供可执行的机器状态

#### 严格要求

不要把同一类信息同时写进两边。

例如：

- 订单号、物流单号、查询类型这类结构化状态，只进 `task_state`
- “用户在查物流”“物流已完成”“当前无待处理任务”这类语义总结，只进 `summary`

---

### `preference` 设计原则

用于记录用户长期偏好。

**典型字段**：

- 喜欢简洁回答
- 偏好中文
- 希望展示时带金额单位
- 喜欢某种表达风格

**触发条件**：必须高置信度才能写入，不要每轮都更新。

**更新策略**：覆盖写，识别到稳定偏好后更新。

---

### `fact` 设计原则

用于记录相对稳定的事实。

**典型字段**：

- `shipping_address`：用户确认过的收货地址
- `phone_verified`：手机号是否已验证
- `preferred_contact_method`：偏好的联系方式

**触发条件**：事实被用户明确确认后才能写入。

**更新策略**：覆盖写或按 key 更新。

---

## 记忆写入与读取规则

### 写入原则

记忆写入的目标不是记录所有信息，而是把“后续对话仍然有价值”的内容保留下来。

#### 写入 `summary`

`summary` 只写入经过提炼后的会话状态，而不是原始过程。

**适合写入的内容**：

- 当前对话主题
- 当前任务目标
- 当前任务进展
- 已确认的关键事实
- 后续回答必须依赖的少量对象标识

**不适合写入的内容**：

- 原始聊天流水
- 工具输出全文
- 未确认的推测
- 一次性临时中间结果
- 与后续无关的噪声

#### 写入 `task_state`

`task_state` 用来记录当前任务的可执行状态，适合从工具调用和工具结果中自动提取。

**典型内容**：

- `last_query_type`
- `last_order_id`
- `last_action`
- `awaiting_user_confirmation`

#### 写入 `preference`

`preference` 只记录高置信度、长期稳定的用户偏好。

**适合写入的内容**：

- 偏好中文
- 偏好简洁回答
- 偏好某种展示格式

#### 写入 `fact`

`fact` 只记录用户明确确认过、且后续仍可复用的稳定事实。

**适合写入的内容**：

- 收货地址
- 联系方式偏好
- 已验证状态

---

### `summary` 压缩规则

`summary` 不是全文压缩器，而是一个“会话级状态摘要”。

#### 压缩目标

压缩后应保留以下信息：

- 当前任务是什么
- 当前目标是什么
- 当前进展到哪一步
- 当前依赖的关键对象是什么
- 下一步需要做什么

#### 压缩粒度

压缩结果应满足：

- 短
- 稳定
- 面向未来
- 不包含过程噪声

#### 不压缩的内容

以下内容不应该进入 `summary`：

- 工具返回的原始长文本
- 完整对话复述
- 调试日志
- 错误堆栈
- 临时推理过程
- 重复背景信息

---

### 避免重复压缩

`summary` 更新时要避免把已有内容反复写进去。

#### 规则 1：只写变化

如果本轮没有新的关键信息，就不要更新 `summary`。

#### 规则 2：保持固定槽位

建议只保留这些语义槽位：

- `topic`
- `goal`
- `current_state`
- `key_ids`
- `next_action`

#### 规则 3：增量合并

更新时基于“旧 `summary` + 本轮新增关键信息”生成新版本，避免重复描述。

#### 规则 4：状态变化才重写

只有在以下情况才值得重写：

- 任务阶段变化
- 任务目标变化
- 关键对象变化
- 任务从进行中变为完成 / 等待 / 失败

---

### 记忆读取规则

记忆读取时要区分“长期稳定信息”和“当前任务状态”。

#### 读取 `summary`

用于恢复当前会话的高层上下文。

**读取目的**：

- 让 Agent 快速知道当前在做什么
- 避免重新推导已确认过的上下文
- 减少对长历史消息的依赖

#### 读取 `task_state`

用于恢复当前任务的执行状态。

**读取目的**：

- 让 Agent 继续上一轮未完成的动作
- 识别当前正在处理的对象
- 判断是否需要继续追问用户

#### 读取 `preference`

用于调整回复风格和表达方式。

**读取目的**：

- 控制回答长度
- 控制语言风格
- 控制展示格式

#### 读取 `fact`

用于补全用户长期稳定信息。

**读取目的**：

- 减少重复询问
- 支持跨轮次引用稳定事实
- 提高上下文复用率

---

### 读取顺序建议

建议按以下顺序读取：

1. `summary`
2. `task_state`
3. `preference`
4. `fact`
5. 最近消息历史

原因是：

- `summary` 提供会话主线
- `task_state` 提供当前动作状态
- `preference` 和 `fact` 提供稳定辅助信息
- 最近消息历史用于补足刚发生的细节

---

### 实现层建议

在 `process_agent_message()` 中，建议把记忆处理拆成两段：

- **读记忆**：在构建 `AgentState` 前加载 `summary / task_state / preference / fact`
- **写记忆**：在 Agent 返回后，根据本轮结果决定是否更新 `summary` 和其他 memory

这样可以保证：

- 读取阶段专注于上下文恢复
- 写入阶段专注于信息筛选和压缩
- 避免每轮都把全部内容重写一遍

---

## 完整一轮对话示例

### 用户第一轮："查我的订单"

```
load_memory → memory 为空 → call_llm → LLM 返回 tool_call(query_orders)
→ execute_tool → 调 order_service → ToolMessage("订单1: 已签收 299元...")
→ call_llm → LLM 返回文字 "您有 4 个订单，最新的是..."
→ save_memory → memory["last_query"] = "list_orders"
→ END → 返回给前端
```

### 用户第二轮："第2个到哪了"

```
load_memory → memory["last_query"] = "list_orders"
→ call_llm → LLM 从 context 知道"第2个"指订单 202605280002
  → 返回 tool_call(query_logistics, {order_id: 11})
→ execute_tool → 调 order_service
→ call_llm → LLM 返回 "订单 202605280002 正在运输中..."
→ save_memory
→ END
```

---

## 前端看到的（无感知）

前端只看到：

```
用户: 查我的订单
Agent: 您有 4 个订单，最新的是 202605280001，已签收 ¥299.00

用户: 第2个到哪了
Agent: 订单 202605280002 正在运输中，中通快递 ZT9876543210
```

前后端之间的 LangGraph 循环对前端完全透明。
