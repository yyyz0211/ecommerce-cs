"""候选结果融合：去重、合并来源和归一化后的分数。"""

from __future__ import annotations

from typing import Iterable

from app.rag.schemas import RetrievalCandidate


def merge_candidates(*candidate_groups: Iterable[RetrievalCandidate]) -> list[RetrievalCandidate]:
    """按文档 ID 合并多个召回通道，同时保留各通道的分数证据。"""
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
