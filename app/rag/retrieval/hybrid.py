"""多路召回编排，只负责召回，不负责融合和重排。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.rag.retrieval.dense import retrieve_dense
from app.rag.retrieval.sparse import retrieve_sparse
from app.rag.schemas import RetrievalCandidate, RetrievalPlan


@dataclass
class RetrievalChannels:
    """各召回通道的原始候选结果。"""

    dense_faq: list[RetrievalCandidate] = field(default_factory=list)
    dense_chunk: list[RetrievalCandidate] = field(default_factory=list)
    sparse: list[RetrievalCandidate] = field(default_factory=list)


def retrieve_candidates(
    plan: RetrievalPlan,
    query_embedding: list[float],
    *,
    dense_top_k: int,
    sparse_top_k: int,
) -> RetrievalChannels:
    """执行向量召回和 BM25 召回，返回未融合的通道结果。"""
    dense_faq, dense_chunk = retrieve_dense(plan, query_embedding, top_k=dense_top_k)
    sparse = retrieve_sparse(plan, top_k=sparse_top_k)
    return RetrievalChannels(dense_faq=dense_faq, dense_chunk=dense_chunk, sparse=sparse)
