"""Select grounded contexts from reranked RAG candidates."""

from __future__ import annotations

from app.rag.schemas import ContextSelection, RetrievalCandidate


def select_contexts(
    candidates: list[RetrievalCandidate],
    *,
    query: str = "",
    top_k: int = 3,
    max_chars: int = 2400,
) -> ContextSelection:
    """Pick contexts for answer generation with FAQ diversity.

    The first pass keeps only one chunk per FAQ to avoid spending the whole
    prompt budget on near-duplicate chunks from the same article. If budget is
    still available, the second pass allows additional chunks from strong FAQs.
    """
    selected: list[RetrievalCandidate] = []
    selected_ids: set[str] = set()
    used_faqs: set[str] = set()
    total_chars = 0

    def can_add(candidate: RetrievalCandidate) -> bool:
        return candidate.id not in selected_ids and total_chars + len(candidate.text) <= max_chars

    for candidate in candidates:
        if len(selected) >= top_k:
            break
        if candidate.faq_id in used_faqs:
            continue
        if not can_add(candidate):
            continue
        selected.append(candidate)
        selected_ids.add(candidate.id)
        used_faqs.add(candidate.faq_id)
        total_chars += len(candidate.text)

    for candidate in candidates:
        if len(selected) >= top_k:
            break
        if not can_add(candidate):
            continue
        selected.append(candidate)
        selected_ids.add(candidate.id)
        total_chars += len(candidate.text)

    if not selected:
        coverage = "none"
    elif len(selected) >= len(candidates):
        coverage = "full"
    else:
        coverage = "partial"

    return ContextSelection(query=query, contexts=selected, coverage=coverage, total_chars=total_chars)
