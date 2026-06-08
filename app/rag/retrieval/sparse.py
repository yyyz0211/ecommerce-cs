"""BM25 关键词召回器。"""

from __future__ import annotations

from app.rag.indexing.keyword_store import search_keyword_index
from app.rag.schemas import RetrievalCandidate, RetrievalPlan


def retrieve_sparse(plan: RetrievalPlan, *, top_k: int) -> list[RetrievalCandidate]:
    """从 BM25 索引召回关键词匹配候选结果。

    分类只作为后续重排信号，不在 BM25 召回阶段硬过滤。
    """
    try:
        return search_keyword_index(plan.primary_query, top_k=top_k, category=None)
    except FileNotFoundError:
        return []
