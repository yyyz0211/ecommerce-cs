# Current System Spec

> **SDD 基准文档**：后续开发必须先对照本文件确认当前系统边界，再写 spec delta / plan / tests。  
> **当前日期**：2026-06-10  
> **项目定位**：电商智能客服学习项目，核心目标是掌握 FastAPI、React、MySQL、LangGraph Agent、自研 RAG、评测驱动优化。  
> **运行环境**：Python 3.9.6；类型注解必须兼容 Python 3.9，禁止新增 `str | None` 这类 Python 3.10 union 写法。  

---

## 1. 系统目标

本项目是一个电商智能客服系统。用户通过前端聊天窗口或传统页面完成注册登录、订单查询、物流查询、售后申请、FAQ 咨询等操作。

当前系统由四条主链路组成：

1. **传统业务 API**：FastAPI + SQLAlchemy async + MySQL，负责用户、订单、物流、售后、会话、消息。
2. **Agent 对话链路**：LangGraph 编排 LLM、工具调用、任务状态、会话记忆。
3. **FAQ RAG 链路**：京东帮助中心 FAQ 数据清洗、关键词打标、Dense + BM25 混合检索、RRF 融合、规则重排、证据选择。
4. **评测链路**：真实 production-like 测试集，记录 V0 到 V7 多版本 RAG 指标，用数据驱动优化。

系统不是生产级商用客服系统；当前优先级是工程结构清晰、可解释、可测试、可迭代。

---

## 2. 技术栈

| 层级 | 技术 | 当前职责 |
|---|---|---|
| 后端 | FastAPI | HTTP API 入口 |
| ORM | SQLAlchemy 2.0 async | MySQL 异步读写 |
| 数据库 | MySQL | 用户、订单、售后、对话、记忆 |
| 前端 | React + Vite | 登录、注册、聊天、订单、售后、个人信息 |
| Agent | LangGraph + langchain-core messages | ReAct 工具调用循环 |
| LLM | OpenAI-compatible Chat API | Agent 回复、工具调用、摘要等 |
| Embedding | OpenAI-compatible Embedding API | FAQ Dense 检索 |
| 向量库 | Chroma | FAQ / chunk 向量集合 |
| 稀疏检索 | jieba + rank-bm25 | 中文 BM25，受控关键词增强 |
| 测试 | pytest / pytest-asyncio | 单元测试、RAG 评测 |

---

## 3. 目录职责

| 路径 | 职责 |
|---|---|
| `app/main.py` | FastAPI app 创建、路由注册、数据库初始化、全局异常处理 |
| `app/config.py` | `.env` 配置加载；数据库、JWT、LLM、Embedding、RAG 路径 |
| `app/models/` | SQLAlchemy 表结构 |
| `app/schemas/` | FastAPI 请求/响应 Pydantic schema |
| `app/routers/` | HTTP 路由层，只做参数解析和 service 调用 |
| `app/services/` | 业务逻辑层，处理数据库读写、权限、事务 |
| `app/agent/` | Agent 状态图、工具、提示词、任务状态机 |
| `app/rag/` | 自研 RAG 系统 |
| `scripts/` | 数据爬取、清洗、建索引、评测、调试脚本 |
| `data/` | FAQ 原始数据、清洗数据、关键词数据、评测结果 |
| `tests/` | 单元测试和 RAG 评测测试 |
| `docs/superpowers/specs/` | SDD spec 文档 |
| `docs/superpowers/plans/` | SDD implementation plan 文档 |

---

## 4. 业务 API 当前系统

### 4.1 用户与鉴权

核心文件：

- `app/routers/auth.py`
- `app/routers/users.py`
- `app/services/auth_service.py`
- `app/services/user_service.py`
- `app/models/user.py`

当前能力：

- 用户注册
- 用户登录
- JWT 签发与刷新
- 当前用户信息查询
- 用户资料修改

设计约束：

- 路由层不写复杂业务逻辑。
- 鉴权依赖统一由 service / dependency 处理。
- 错误返回必须使用 `app/errors.py` 中的统一错误结构。

### 4.2 订单与物流

核心文件：

- `app/routers/orders.py`
- `app/services/order_service.py`
- `app/models/order.py`

当前能力：

- 订单分页列表
- 订单详情
- 测试订单创建
- 订单取消
- 物流查询

设计约束：

- 订单查询必须校验 `user_id`，不能跨用户访问。
- 订单状态变更必须在 service 层集中处理。
- Agent 工具调用订单能力时，也必须走 service 层，不能绕过业务规则直接查表。

### 4.3 售后

核心文件：

- `app/routers/after_sale.py`
- `app/services/after_sale_service.py`
- `app/models/after_sale.py`

当前能力：

- 提交售后申请
- 售后列表
- 售后详情

设计约束：

- 售后必须关联用户订单。
- 售后状态流转不要散落在 Agent prompt 里，应由 service 层保证。

---

## 5. Agent 当前系统

### 5.1 Agent 图结构

核心文件：

- `app/agent/core/graph.py`
- `app/agent/core/runtime.py`
- `app/agent/tools/ecommerce.py`
- `app/agent/prompts.py`
- `app/agent/schemas/task_state.py`
- `app/services/chat_service.py`
- `app/services/memory_service.py`

当前 LangGraph 流程：

```text
START
  ↓
load_memory
  ↓
call_llm
  ├─ 有 tool_call → execute_tool → call_llm
  └─ 无 tool_call → END
```

关键规则：

- `load_memory_node` 只读记忆，不写记忆。
- 主链路在 `chat_service.process_agent_message()` 保存用户消息和 Agent 回复。
- `task_state` 主链路保存失败时，后台任务兜底保存。
- 工具调用上限是 `MAX_TOOL_ITERATIONS = 4`，避免 LLM 无限循环。
- 工具参数 schema 来自 LangChain tool 的 `args_schema`，不要手写两份参数定义。

### 5.2 Agent 工具

核心文件：

- `app/agent/tools/ecommerce.py`

当前工具覆盖：

- 订单查询
- 订单详情
- 物流查询
- 售后申请
- FAQ RAG 检索

工具设计约束：

- 工具返回必须结构化，便于 LLM 二次总结。
- 工具日志要短，不要把长答案全部打进日志。
- FAQ 检索结果中保留 `keywords`、`matched_keywords`、`sources`、`reasons`，用于可解释排查。

### 5.3 任务状态与记忆

核心文件：

- `app/agent/schemas/task_state.py`
- `app/agent/core/state_machine.py`
- `app/services/memory_service.py`

当前记忆类型：

- `summary`
- `task_state`
- `preference`
- `fact`
- `cursor`

设计约束：

- `task_state` 是结构化任务状态，不要退回纯文本状态。
- 记忆写入由 service 层统一处理，Graph 节点内只读。
- 数据库层可能存在历史重复记忆，保存逻辑要考虑 upsert 和唯一性约束。

---

## 6. RAG 当前系统

### 6.1 RAG 分层

核心目录：

```text
app/rag/
  planning/       query 分析与检索计划
  indexing/       数据加载、embedding、BM25、关键词词库、Chroma
  retrieval/      dense / sparse / hybrid 召回
  reranking/      规则重排
  evidence/       最终证据选择
  pipeline.py     六层流程编排
  service.py      对外 JSON 服务接口
```

当前 RAG 主流程：

```text
用户 query
  ↓
Query Planner
  ↓
Embedding query
  ↓
Dense FAQ 召回 + Dense Chunk 召回 + BM25 召回
  ↓
RRF Fusion
  ↓
Rule Rerank
  ↓
Evidence Selector
  ↓
返回 matches + trace_counts + reasons
```

入口函数：

- `app/rag/pipeline.py::run_rag_pipeline`
- `app/rag/service.py::search_faq_knowledge`

### 6.2 Query Planning

核心文件：

- `app/rag/planning/analyzer.py`
- `app/rag/planning/planner.py`

当前能力：

- 归一化 query
- 推断分类
- 抽取关键词
- 生成 primary query

设计约束：

- 分类只能作为 soft boost 或 trace 信息，不能在召回阶段 hard filter。
- 原始 query 必须保留，不能只保留 rewrite 后 query。
- 后续如果引入 LLM query rewrite，必须保留原 query、rewrite query、结构化 intent，便于调试。

### 6.3 Dense 检索

核心文件：

- `app/rag/indexing/embeddings.py`
- `app/rag/indexing/vector_store.py`
- `app/rag/retrieval/dense.py`
- `scripts/build_jd_faq_chroma.py`

Chroma 集合：

- `CHROMA_DOC_COLLECTION`：FAQ 级别文档
- `CHROMA_CHUNK_COLLECTION`：chunk 级别文档

Embedding 文本构造：

```text
分类：...
问题：...
关键词：...
正文...
```

设计约束：

- Chroma 存储的 document 仍是原文 `text`。
- 分类、问题、关键词只用于 embedding 文本增强，不替代原始内容。
- 默认构建输入必须使用关键词增强文件：
  - `data/jd_faq_clean_keywords.jsonl`
  - `data/jd_faq_chunks_keywords.jsonl`

### 6.4 BM25 / Sparse 检索

核心文件：

- `app/rag/indexing/keyword_store.py`
- `app/rag/indexing/keyword_vocabulary.py`
- `app/rag/retrieval/sparse.py`
- `scripts/build_jd_faq_keyword_index.py`

当前设计：

- jieba 负责中文分词。
- `STOPWORDS` 负责过滤工程噪声词。
- `KEYWORD_VOCAB_PATH` 指向正式关键词词库。
- `get_protected_terms()` 从词库派生 jieba 保护词。
- `tokenize_query()` 当前返回：

```python
raw_tokens + mapped_keyword_tokens
```

- `tokenize_document()` 当前字段权重：

```text
category       x2
question       x5
section_title  x3
keywords       x4
text           x1
```

设计约束：

- 不要把 BM25 分词逻辑和 LLM 调用混在一起。
- LLM 只参与离线词库生成；线上 BM25 必须稳定、可复现、低延迟。
- 后续如果优化 query token，应先做 A/B 测试：
  - 当前：`raw_tokens + keyword_tokens`
  - 建议候选：`keyword_tokens * N + raw_tokens`
  - 激进候选：`keyword_tokens only`

### 6.5 关键词词库

核心文件：

- `app/rag/indexing/keyword_taxonomy.py`
- `app/rag/indexing/keyword_vocabulary.py`
- `app/rag/indexing/llm_keyword_mining.py`
- `scripts/build_jd_faq_keyword_vocab.py`
- `scripts/annotate_jd_faq_keywords.py`
- `scripts/mine_jd_faq_keyword_expressions_llm.py`
- `scripts/cluster_jd_faq_keyword_expressions_llm.py`

当前数据：

- `data/jd_faq_keyword_vocab.json`
- `data/jd_faq_clean_keywords.jsonl`
- `data/jd_faq_chunks_keywords.jsonl`

当前统计：

| 文件 | 总数 | 有 keywords |
|---|---:|---:|
| `data/jd_faq_clean_keywords.jsonl` | 350 | 279 |
| `data/jd_faq_chunks_keywords.jsonl` | 385 | 360 |

当前关键词流程：

```text
规则词库 / LLM 候选词库
  ↓
构建正式 keyword vocabulary
  ↓
FAQ 级别打 keywords
  ↓
chunk 级别打 keywords，并继承 FAQ keywords
  ↓
BM25 / Chroma / rerank / service 共同消费 keywords
```

LLM 关键词设计方向：

```text
LLM 离线统计原始表达
  ↓
LLM 聚类归一化
  ↓
人工/规则审核
  ↓
正式关键词词库
  ↓
文档受控打标
```

设计约束：

- 不允许每次线上 query 都调用 LLM 做分词。
- 不允许让 LLM 任意生成文档 keywords 后直接入库，必须受控词库约束。
- 关键词要尽量表达业务概念，不要保留“商品/问题/服务/用户/订单”等泛词。

### 6.6 Fusion / Rerank / Evidence

核心文件：

- `app/rag/retrieval/fusion.py`
- `app/rag/reranking/rule.py`
- `app/rag/evidence/selector.py`

当前策略：

- Fusion 使用 RRF，不直接混用 dense_score 和 bm25_score。
- Rerank 使用可解释规则：
  - fusion_score
  - category soft match
  - keyword overlap
  - question exact
  - dense + bm25 hybrid hit
  - FAQ level bonus
- Evidence selector 控制最终上下文数量和字符预算。

设计约束：

- 不允许在 fusion 阶段直接把 dense 分数和 BM25 分数相加。
- rerank reasons 必须保留，方便 CLI / 接口排查。
- evidence selector 要避免一个 FAQ 的多个相似 chunk 占满上下文预算。

---

## 7. 数据资产

### 7.1 京东 FAQ 数据

| 文件 | 说明 |
|---|---|
| `data/jd_faq.jsonl` | 原始爬取数据 |
| `data/jd_faq.csv` | 原始爬取 CSV |
| `data/jd_faq_clean.jsonl` | 清洗后 FAQ |
| `data/jd_faq_clean.csv` | 清洗后 CSV |
| `data/jd_faq_chunks.jsonl` | 原始 chunk |
| `data/jd_faq_keyword_vocab.json` | 当前正式关键词词库 |
| `data/jd_faq_clean_keywords.jsonl` | FAQ 级别关键词增强数据 |
| `data/jd_faq_chunks_keywords.jsonl` | chunk 级别关键词增强数据 |

### 7.2 评测数据

| 文件 | 说明 |
|---|---|
| `data/rag_eval/production_like_cases.jsonl` | 100 条真实风格评测用例 |
| `data/rag_eval/production_like_eval_results.json` | 机器可读评测结果 |
| `data/rag_eval/production_like_eval_report.md` | Markdown 评测报告 |
| `data/rag_eval/fusion_rrf_comparison.md` | Fusion 与 RRF 对比记录 |

当前真实评测结果，生成时间 `2026-06-10 11:40:24`：

| 版本 | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---:|---:|---:|---:|
| RAG-V0 关键词基线 | 73.0% | 87.0% | 90.0% | 0.800 |
| RAG-V1 BM25 FAQ | 69.0% | 86.0% | 89.0% | 0.773 |
| RAG-V2 Dense Chunk | 89.0% | 99.0% | 99.0% | 0.940 |
| RAG-V3 Dense FAQ + Dense Chunk | 89.0% | 99.0% | 99.0% | 0.927 |
| RAG-V4 Dense + BM25 混合检索 | 68.0% | 81.0% | 90.0% | 0.746 |
| RAG-V5 混合检索 + Fusion | 81.0% | 93.0% | 96.0% | 0.868 |
| RAG-V6 混合检索 + Fusion + Rule Rerank | 72.0% | 88.0% | 95.0% | 0.808 |
| RAG-V7 当前完整系统 | 73.0% | 93.0% | 94.0% | 0.822 |

V7 Recall@3 未命中 case：

```text
prod_like_002
prod_like_027
prod_like_052
prod_like_066
prod_like_073
prod_like_075
prod_like_088
```

---

## 8. 当前已知问题与优化方向

### 8.1 RAG 指标问题

当前 V7 没有超过 V2 Dense Chunk：

```text
V2 Recall@3 = 99.0%
V7 Recall@3 = 93.0%
```

这说明当前完整系统的 fusion / rerank / evidence selection 仍有优化空间。下一轮 RAG 优化应优先分析 V7 未命中 case，而不是继续堆关键词。

### 8.2 Query Token 设计问题

当前 query token 设计：

```python
raw_tokens + keyword_tokens
```

存在问题：标准关键词信号可能不够强。

候选优化：

```python
keyword_tokens * 4 + raw_tokens
```

但不能直接删除 raw tokens，因为词库覆盖不到的表达仍需要原话分词兜底。

### 8.3 规则 Rerank 风险

V6 / V7 指标说明规则重排可能压低部分正确结果。后续修改 rerank 必须：

- 先新增失败用例或评测 case。
- 对比 V5 / V7 指标变化。
- 保留 `rerank_reasons`，不要只看最终分。

### 8.4 数据与索引一致性

默认构建索引必须使用关键词增强数据：

```text
data/jd_faq_clean_keywords.jsonl
data/jd_faq_chunks_keywords.jsonl
```

如果使用原始 `data/jd_faq_clean.jsonl` / `data/jd_faq_chunks.jsonl`，关键词增强不会进入 BM25 和 Chroma。

---

## 9. SDD 开发框架

后续开发必须遵循 SDD：Spec → Plan → Test → Implement → Verify → Record。

### 9.1 Spec

每次较大改动前，先写或更新 spec。

位置：

```text
docs/superpowers/specs/YYYY-MM-DD-<topic>-spec.md
```

spec 必须包含：

- 当前问题
- 目标行为
- 本次要新增或修改的功能
- 用户如何使用
- 输入输出是什么
- 异常情况怎么处理
- 不做什么
- 影响模块
- 哪些代码要变
- 数据契约
- 测试方式
- 哪些测试要过
- 验收标准
- 评测指标
- 风险和回滚方式

禁止只说“优化 RAG”“提升效果”这类模糊目标。

单功能 spec 必须使用下面的结构：

```markdown
# <功能名> Spec

## 1. 背景与问题

说明当前系统哪里不满足需求，必须引用真实现象、测试结果、用户操作或代码路径。

## 2. 本次新增/修改的功能

明确列出这次要新增或修改什么功能。只写本次范围，不写未来可能做的扩展。

## 3. 用户如何使用

说明用户、开发者或运维如何触发这个功能。
如果是接口功能，写清楚 API 路径或脚本命令。
如果是 RAG 功能，写清楚 query 示例和预期检索行为。

## 4. 输入与输出

写清楚输入字段、输出字段、数据格式、示例。
涉及 Pydantic schema、JSONL、Markdown 报告、CLI 输出时必须给出具体字段。

## 5. 异常情况处理

列出错误输入、空结果、外部 API 失败、文件不存在、索引缺失、权限不足等情况如何处理。
不能只写“做好错误处理”。

## 6. 不做什么

明确本次不解决的内容，避免实现时扩大范围。

## 7. 影响代码

列出预计要新增/修改的文件，以及每个文件的职责变化。

## 8. 测试与验收标准

列出必须新增或修改的测试、必须通过的测试命令、人工验收方式。
验收标准必须可判断，例如“Recall@3 不低于当前基线 93.0%”，而不是“效果更好”。

## 9. 风险与回滚

说明可能破坏什么、如何发现、如何恢复到旧行为。
```

### 9.2 Plan

spec 确认后再写 implementation plan。

位置：

```text
docs/superpowers/plans/YYYY-MM-DD-<topic>.md
```

plan 必须包含：

- 任务拆分
- 每步要改的文件
- 先写哪些测试
- 运行哪些命令
- 预期失败/通过结果
- 是否需要重建索引
- 是否需要重新跑 RAG eval

### 9.3 Test

所有行为变化必须先有测试。

最低要求：

- Python 单元测试：`pytest`
- RAG 关键词相关：`pytest tests/test_rag_keywords.py`
- RAG pipeline 相关：`pytest tests/test_rag_pipeline.py`
- LLM 关键词流程：`pytest tests/test_rag_llm_keyword_mining.py`
- Agent 相关：运行对应 `tests/test_agent_*.py`

RAG 指标变化必须跑：

```bash
/Users/leon/.pyenv/versions/3.9.6/bin/python3 scripts/rag_eval.py \
  --suite production_like \
  --cases data/rag_eval/production_like_cases.jsonl \
  --faq-input data/jd_faq_clean_keywords.jsonl \
  --chunks-input data/jd_faq_chunks_keywords.jsonl \
  --output data/rag_eval/production_like_eval_report.md \
  --json-output data/rag_eval/production_like_eval_results.json
```

### 9.4 Implement

实现规则：

- 保持模块边界，不把 LLM 调用塞进 BM25 分词。
- 不把业务规则写进 prompt，业务校验放 service 层。
- 不直接改生成数据来掩盖代码问题。
- 不删除用户已有改动。
- Python 兼容 3.9。
- 注释使用中文，解释设计意图，不重复代码字面含义。

### 9.5 Verify

提交前至少运行：

```bash
pytest -q
```

如果改了 RAG：

```bash
pytest tests/test_rag_keywords.py tests/test_rag_pipeline.py tests/test_rag_llm_keyword_mining.py -q
```

如果改了脚本：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/my-project-pycache \
/Users/leon/.pyenv/versions/3.9.6/bin/python3 -m py_compile <changed scripts>
```

如果改了 RAG 排序、召回、重排：

- 必须跑真实评测集。
- 必须记录指标变化。
- 必须列出未命中 case。

### 9.6 Record

每次 RAG 优化后，更新：

- `data/rag_eval/production_like_eval_results.json`
- `data/rag_eval/production_like_eval_report.md`
- 必要时新增对比文档，例如 `data/rag_eval/<topic>_comparison.md`

记录必须包含：

- 改动内容
- 测试集
- 指标变化
- 未命中 case
- 是否接受该优化

---

## 10. 后续开发优先级

### P0

- 修正 V7 未命中 case 的根因分析。
- 对 query token 权重做 A/B 测试。
- 优化 rule rerank，避免压低 Dense Chunk 的强召回结果。

### P1

- 增加 CLI 可视化：展示 query planning、dense 召回、BM25 召回、fusion、rerank、evidence。
- 为 RAG eval 增加“按标签统计”，例如支付干扰、物流干扰、多意图。
- 增加关键词词库 review 流程，区分人工确认词和 LLM 新增词。

### P2

- 接入 LangSmith trace，但不强依赖 LangChain RAG 框架。
- 前端增加 RAG debug 页面。
- 增加知识库新增/版本化管理。

---

## 11. 当前系统不变量

后续开发不得破坏以下不变量：

1. `search_faq_knowledge()` 必须返回可 JSON 序列化结构。
2. `RetrievalCandidate` 必须保留 `sources`、`keywords`、`matched_keywords`、`rerank_reasons`。
3. RAG 不允许在召回阶段对 planner 分类做 hard filter。
4. BM25 不直接调用 LLM。
5. Dense、BM25、Fusion、Rerank、Evidence 必须保持可单独测试。
6. 关键词增强数据和原始数据要分开保留。
7. 默认索引构建必须读取 `*_keywords.jsonl`。
8. 评测指标不能只看单条样例，必须看 production-like 全量结果。
9. Python 代码必须兼容 3.9。
10. 所有后续功能开发必须遵循 SDD。
