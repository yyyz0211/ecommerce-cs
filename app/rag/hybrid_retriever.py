"""Hybrid retrieval pipeline for JD FAQ RAG."""

from __future__ import annotations

from typing import Iterable, Optional

from app.config import settings
from app.rag.context_selector import select_contexts
from app.rag.embeddings import embed_query
from app.rag.keyword_store import search_keyword_index
from app.rag.query_analyzer import analyze_query
from app.rag.reranker import rerank_candidates
from app.rag.schemas import RAGMatch, RetrievalCandidate, RetrievalTrace
from app.rag.vector_store import query_documents


def candidate_from_match(match: RAGMatch, source: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        id=match.id,
        faq_id=match.faq_id,
        doc_type=match.doc_type,
        chunk_index=match.chunk_index,
        chunk_count=match.chunk_count,
        source=match.source,
        category=match.category,
        question=match.question,
        text=match.text,
        url=match.url,
        section_title=match.section_title,
        dense_score=match.score,
        sources=[source],
    )


def merge_candidates(*candidate_groups: Iterable[RetrievalCandidate]) -> list[RetrievalCandidate]:
    """Merge recall channels by document id while preserving score evidence."""
    merged: dict[str, RetrievalCandidate] = {}
    for group in candidate_groups:
        for candidate in group:
            existing = merged.get(candidate.id)
            if existing is None:
                merged[candidate.id] = candidate
                continue

            sources = list(existing.sources)
            for source in candidate.sources:
                if source not in sources:
                    sources.append(source)

            dense_scores = [score for score in (existing.dense_score, candidate.dense_score) if score is not None]
            sparse_scores = [score for score in (existing.sparse_score, candidate.sparse_score) if score is not None]
            merged[candidate.id] = existing.model_copy(
                update={
                    "dense_score": max(dense_scores) if dense_scores else None,
                    "sparse_score": max(sparse_scores) if sparse_scores else None,
                    "sources": sources,
                }
            )
    return list(merged.values())


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
        # Chroma can raise before indexes are built. Returning an empty channel
        # keeps the agent usable while CLI/debug scripts expose the missing data.
        return []
    return [candidate_from_match(match, source) for match in matches]


async def retrieve_hybrid(
    query: str,
    *,
    category: Optional[str] = None,
    top_k: int = 3,
    dense_top_k: int = 20,
    sparse_top_k: int = 20,
    max_context_chars: int = 2400,
) -> RetrievalTrace:
    """Run query analysis, double dense recall, BM25 recall, rerank, and selection."""
    analysis = analyze_query(query, category=category)
    retrieval_query = analysis.rewrite_query or analysis.normalized_query or query

    query_embedding = await embed_query(retrieval_query)
    dense_faq = _query_chroma_candidates(
        query_embedding,
        collection_name=settings.CHROMA_DOC_COLLECTION,
        source="dense_faq",
        top_k=dense_top_k,
        category=analysis.category,
    )
    dense_chunk = _query_chroma_candidates(
        query_embedding,
        collection_name=settings.CHROMA_CHUNK_COLLECTION,
        source="dense_chunk",
        top_k=dense_top_k,
        category=analysis.category,
    )

    try:
        sparse = search_keyword_index(retrieval_query, top_k=sparse_top_k, category=analysis.category)
    except FileNotFoundError:
        sparse = []

    merged = merge_candidates(dense_faq, dense_chunk, sparse)
    reranked = rerank_candidates(merged, analysis)
    selection = select_contexts(reranked, query=query, top_k=top_k, max_chars=max_context_chars)

    return RetrievalTrace(
        query=query,
        analysis=analysis,
        dense_faq=dense_faq,
        dense_chunk=dense_chunk,
        sparse=sparse,
        merged=merged,
        reranked=reranked,
        selection=selection,
    )
