"""Service-level helpers for RAG tools."""

from __future__ import annotations

from typing import Optional

from app.rag.hybrid_retriever import retrieve_hybrid


async def search_faq_knowledge(
    query: str,
    *,
    category: Optional[str] = None,
    top_k: int = 3,
    min_score: Optional[float] = None,
) -> dict:
    """Search FAQ knowledge and return a JSON-serializable payload."""
    trace = await retrieve_hybrid(query, top_k=top_k, category=category)
    contexts = trace.selection.contexts
    if min_score is not None:
        contexts = [item for item in contexts if item.final_score is not None and item.final_score >= min_score]
    return {
        "query": trace.query,
        "analysis": trace.analysis.model_dump(),
        "coverage": trace.selection.coverage,
        "trace_counts": {
            "dense_faq": len(trace.dense_faq),
            "dense_chunk": len(trace.dense_chunk),
            "sparse": len(trace.sparse),
            "merged": len(trace.merged),
            "reranked": len(trace.reranked),
            "selected": len(contexts),
        },
        "matches": [
            {
                "id": item.id,
                "faq_id": item.faq_id,
                "doc_type": item.doc_type,
                "title": item.question,
                "category": item.category,
                "content": item.text,
                "url": item.url,
                "score": item.final_score,
                "sources": item.sources,
                "reasons": item.rerank_reasons,
            }
            for item in contexts
        ],
    }
