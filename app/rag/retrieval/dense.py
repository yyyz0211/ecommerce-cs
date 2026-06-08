"""Chroma 向量召回器。"""

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.rag.schemas import RAGMatch, RetrievalCandidate, RetrievalPlan
from app.rag.indexing.vector_store import query_documents


def candidate_from_match(match: RAGMatch, source: str) -> RetrievalCandidate:
    """把原始向量召回结果转换成统一候选结果。"""
    payload = match.model_dump(exclude={"distance", "score", "retrieval_source"})
    return RetrievalCandidate(**payload, dense_score=match.score, sources=[source])


def _query_chroma_candidates(
    query_embedding: list[float],
    *,
    collection_name: str,
    source: str,
    top_k: int,
    category: Optional[str],
) -> list[RetrievalCandidate]:
    try:
        matches = query_documents(
            query_embedding,
            top_k=top_k,
            category=category,
            collection_name=collection_name,
        )
    except Exception:
        # Chroma 索引尚未构建时可能抛错；这里返回空通道，让 Agent 仍可继续工作。
        # 具体缺失情况会通过 CLI/debug 脚本暴露出来。
        return []
    return [candidate_from_match(match, source) for match in matches]


def retrieve_dense(
    plan: RetrievalPlan,
    query_embedding: list[float],
    *,
    top_k: int,
) -> tuple[list[RetrievalCandidate], list[RetrievalCandidate]]:
    """分别从 FAQ 级别和 chunk 级别 Chroma 集合召回候选结果。

    planner 推断出的分类只作为后续重排的软信号，不在召回阶段做硬过滤。
    否则一旦分类误判，正确 FAQ 会在初始召回阶段被直接丢弃。
    """
    dense_faq = _query_chroma_candidates(
        query_embedding,
        collection_name=settings.CHROMA_DOC_COLLECTION,
        source="dense_faq",
        top_k=top_k,
        category=None,
    )
    dense_chunk = _query_chroma_candidates(
        query_embedding,
        collection_name=settings.CHROMA_CHUNK_COLLECTION,
        source="dense_chunk",
        top_k=top_k,
        category=None,
    )
    return dense_faq, dense_chunk
