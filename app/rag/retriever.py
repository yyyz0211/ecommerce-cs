"""Backward-compatible FAQ retrieval helpers."""

from __future__ import annotations

from typing import Optional

from app.rag.hybrid_retriever import retrieve_hybrid
from app.rag.query_analyzer import infer_category
from app.rag.schemas import RAGMatch, RAGSearchResult


async def search_faq(
    query: str,
    *,
    top_k: int = 5,
    category: Optional[str] = None,
    min_score: Optional[float] = None,
) -> RAGSearchResult:
    """Search JD FAQ knowledge through the hybrid pipeline."""
    trace = await retrieve_hybrid(query, top_k=top_k, category=category)
    matches = [
        RAGMatch(
            id=item.id,
            faq_id=item.faq_id,
            doc_type=item.doc_type,
            chunk_index=item.chunk_index,
            chunk_count=item.chunk_count,
            source=item.source,
            category=item.category,
            question=item.question,
            text=item.text,
            url=item.url,
            section_title=item.section_title,
            score=item.final_score,
            retrieval_source="+".join(item.sources),
        )
        for item in trace.selection.contexts
    ]
    if min_score is not None:
        matches = [match for match in matches if match.score is not None and match.score >= min_score]
    return RAGSearchResult(query=query, matches=matches)
