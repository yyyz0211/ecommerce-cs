"""候选结果融合：用 RRF 去重并合并多路召回结果。"""

from __future__ import annotations

from typing import Iterable

from app.rag.schemas import RetrievalCandidate

RRF_K = 60


def merge_candidates(*candidate_groups: Iterable[RetrievalCandidate]) -> list[RetrievalCandidate]:
    """按文档 ID 合并多个召回通道，并用 RRF 计算融合分。

    RRF 只依赖各通道内部排名，不直接比较 dense_score 和 bm25_score 的绝对值。
    这能避免不同召回通道分数尺度不一致导致的错误排序。
    """
    merged: dict[str, RetrievalCandidate] = {}
    rrf_scores: dict[str, float] = {}

    for group in candidate_groups:
        group_candidates = list(group)
        for rank, candidate in enumerate(group_candidates, start=1):
            rrf_scores[candidate.id] = rrf_scores.get(candidate.id, 0.0) + 1.0 / (RRF_K + rank)
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

    max_rrf = max(rrf_scores.values(), default=0.0) or 1.0
    fused = [
        candidate.model_copy(update={"fusion_score": round(rrf_scores[candidate_id] / max_rrf, 6)})
        for candidate_id, candidate in merged.items()
    ]
    return sorted(
        fused,
        key=lambda item: (
            item.fusion_score or 0.0,
            len(item.sources),
            item.dense_score or 0.0,
            item.sparse_score or 0.0,
        ),
        reverse=True,
    )
