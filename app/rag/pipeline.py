"""RAG 主管道：只负责编排六层流程。"""

from __future__ import annotations

from typing import Optional

from app.rag.indexing.embeddings import embed_query
from app.rag.evidence.selector import select_evidence
from app.rag.retrieval.fusion import merge_candidates
from app.rag.planning.planner import plan_query
from app.rag.reranking.rule import rerank_candidates
from app.rag.retrieval.hybrid import retrieve_candidates
from app.rag.schemas import RetrievalTrace


async def run_rag_pipeline(
    query: str,
    *,
    category: Optional[str] = None,
    top_k: int = 3,
    dense_top_k: int = 20,
    sparse_top_k: int = 20,
    max_context_chars: int = 2400,
) -> RetrievalTrace:
    """执行 Query Planner、Retriever、Fusion、Reranker、Evidence Selector。"""
    plan = plan_query(query, category=category)
    query_embedding = await embed_query(plan.primary_query)
    channels = retrieve_candidates(
        plan,
        query_embedding,
        dense_top_k=dense_top_k,
        sparse_top_k=sparse_top_k,
    )
    merged = merge_candidates(channels.dense_faq, channels.dense_chunk, channels.sparse)
    reranked = rerank_candidates(merged, plan)
    selection = select_evidence(reranked, query=query, top_k=top_k, max_chars=max_context_chars)

    return RetrievalTrace(
        query=query,
        analysis=plan,
        dense_faq=channels.dense_faq,
        dense_chunk=channels.dense_chunk,
        sparse=channels.sparse,
        merged=merged,
        reranked=reranked,
        selection=selection,
    )
