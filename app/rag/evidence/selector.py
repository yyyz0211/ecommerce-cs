"""从重排后的 RAG 候选中选择可作为依据的上下文。"""

from __future__ import annotations

from app.rag.schemas import ContextSelection, RetrievalCandidate


def select_contexts(
    candidates: list[RetrievalCandidate],
    *,
    query: str = "",
    top_k: int = 3,
    max_chars: int = 2400,
) -> ContextSelection:
    """为答案生成选择上下文，同时保持 FAQ 来源多样性。

    第一轮每个 FAQ 只保留一个 chunk，避免把 prompt 预算都花在同一篇文章的相似片段上。
    如果预算仍然充足，第二轮再允许从高分 FAQ 中补充更多 chunk。
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


def select_evidence(
    candidates: list[RetrievalCandidate],
    *,
    query: str = "",
    top_k: int = 3,
    max_chars: int = 2400,
) -> ContextSelection:
    """选择最终提供给 Agent/LLM 的证据上下文。"""
    return select_contexts(candidates, query=query, top_k=top_k, max_chars=max_chars)
