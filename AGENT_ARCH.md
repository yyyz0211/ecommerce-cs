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
      result = format_orders(orders)        # 转为文字

  elif tool_name == "query_logistics":
      logistics = await get_order_logistics(db, ...)
      result = format_logistics(logistics)

  elif tool_name == "submit_after_sale":
      record = await create_after_sale(db, ...)
      result = f"售后已提交，编号 {record.id}"

  elif tool_name == "transfer_to_human":
      transfer_log = create_transfer_log(db, ...)
      conversation.status = "transferred"
      result = "已转接人工客服"

  # 工具结果作为 ToolMessage 追加到 state
  state.messages.append(ToolMessage(content=result, tool_call_id=tool_call.id))

输出: state.messages（多了 ToolMessage）
→ 返回 call_llm 节点，让 LLM 基于结果生成回复
```

---

### 5. save_memory

```
操作: 分析本轮对话，提取关键信息
  → 如果用户查了某个订单 → memory["last_order_id"] = order.id
  → 如果用户问了物流 → memory["last_query_type"] = "logistics"
  → 如果是首次对话 → memory["returning_user"] = True
  ...
  写入 memory 表或更新 state.memory
```

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
