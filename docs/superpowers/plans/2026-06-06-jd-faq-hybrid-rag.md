# 京东 FAQ 混合 RAG 实现计划

> **给后续执行者：** 如需继续按任务推进，建议使用 `superpowers:subagent-driven-development`，也可以使用 `superpowers:executing-plans`。每个步骤使用复选框（`- [ ]`）跟踪状态。

**目标：** 构建一个可调试的京东 FAQ RAG 系统，包含 query 理解、FAQ/Chunk 双层索引召回、中文 BM25、可解释重排、基于证据的上下文选择，以及 CLI 检索链路可视化。

**架构：** 保持 Agent 工具层调用方式稳定，把 RAG 内部逻辑拆成多个小模块。向量召回使用 Chroma，同时维护 FAQ 级别集合和 Chunk 级别集合；关键词召回使用本地 BM25 索引；第一版重排和上下文选择先采用确定性规则实现，并在关键位置注释后续可接入 LLM query 改写和模型 rerank 的扩展点。

**技术栈：** Python、Pydantic、Chroma、OpenAI-compatible embedding API、jieba、rank-bm25、pytest。

---

### 任务 1：数据契约和测试

**文件：**
- 新建：`tests/test_rag_pipeline.py`
- 修改：`app/rag/schemas.py`

- [ ] 为 query 分析、BM25 分词行为、候选结果合并、重排解释、上下文选择编写测试。
- [ ] 运行 `pytest tests/test_rag_pipeline.py -q`，确认测试因为新模块尚未实现而失败。

### 任务 2：Query 理解

**文件：**
- 新建：`app/rag/query_analyzer.py`
- 修改：`app/rag/retriever.py`

- [ ] 实现基于规则的 query 归一化、分类推断、关键词抽取和业务工具提示。
- [ ] 保持规则显式可读，并在关键位置添加注释，因为这些规则决定了模型调用前的检索意图。

### 任务 3：稀疏索引

**文件：**
- 新建：`app/rag/keyword_store.py`
- 新建：`scripts/build_jd_faq_keyword_index.py`
- 修改：`requirements.txt`

- [ ] 增加 `jieba` 和 `rank-bm25` 依赖。
- [ ] 实现中文分词，加入领域词保护和停用词过滤。
- [ ] 将 BM25 语料持久化到 `data/jd_faq_bm25.pkl`。

### 任务 4：混合召回和重排

**文件：**
- 新建：`app/rag/hybrid_retriever.py`
- 新建：`app/rag/reranker.py`
- 新建：`app/rag/context_selector.py`
- 修改：`app/rag/vector_store.py`
- 修改：`app/rag/service.py`

- [ ] 分别从 FAQ Chroma、Chunk Chroma 和 BM25 执行独立召回。
- [ ] 按文档 ID 合并候选结果，保留召回来源、向量分数和稀疏分数。
- [ ] 使用可解释的确定性特征进行重排，包括分类匹配、关键词重叠、问题精确命中、向量分数、BM25 分数、FAQ/Chunk 偏好。
- [ ] 选择用于答案生成的 grounding contexts，同时控制 FAQ 多样性和最大字符预算。

### 任务 5：索引构建和 CLI 调试

**文件：**
- 修改：`scripts/build_jd_faq_chroma.py`
- 新建：`scripts/rag_debug_query.py`

- [ ] 同时构建 FAQ 级别和 Chunk 级别的 Chroma 索引。
- [ ] 在 CLI 中打印 query 分析、各召回通道、合并候选、重排候选和最终选中的上下文。

### 任务 6：验证

**命令：**
- `pytest tests/test_rag_pipeline.py -q`
- `python3 -m py_compile app/rag/*.py scripts/build_jd_faq_chroma.py scripts/build_jd_faq_keyword_index.py scripts/rag_debug_query.py`
- `pytest tests/test_agent_tools.py tests/test_agent_graph.py tests/test_agent_state_machine.py -q`
