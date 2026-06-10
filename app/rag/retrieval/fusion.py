"""候选结果融合：用 RRF 去重并合并多路召回结果。"""

from __future__ import annotations

from typing import Iterable, Optional

from app.rag.schemas import RetrievalCandidate

RRF_K = 60
BM25_SPARSE_ONLY_WEIGHT = 0.2


def _merge_sources(*source_groups: Iterable[str]) -> list[str]:
    """按出现顺序合并召回来源，避免 sources 里出现重复通道名。"""
    merged: list[str] = []
    for sources in source_groups:
        for source in sources:
            if source not in merged:
                merged.append(source)
    return merged


def _best_sparse_by_faq(candidates: Iterable[RetrievalCandidate]) -> dict[str, RetrievalCandidate]:
    """每个 FAQ 只保留 BM25 分数最高的候选。

    Dense 召回常返回 chunk，BM25 可能返回 FAQ 或 chunk。
    V5d 的 boost 关注的是“同一个 FAQ 是否也被 BM25 命中”，所以这里按 faq_id 聚合。
    """
    best: dict[str, RetrievalCandidate] = {}
    for candidate in candidates:
        current = best.get(candidate.faq_id)
        if current is None or (candidate.sparse_score or 0.0) > (current.sparse_score or 0.0):
            best[candidate.faq_id] = candidate
    return best


def merge_candidates_dense_primary(
    dense_candidates: Iterable[RetrievalCandidate],
    sparse_candidates: Iterable[RetrievalCandidate],
    *,
    same_faq_boost: float = 0.02,
    sparse_only_weight: float = BM25_SPARSE_ONLY_WEIGHT,
) -> list[RetrievalCandidate]:
    """V5d 融合策略：Dense 主排序，BM25 只做轻量辅助。

    这个策略来自评测中表现更稳的 V5d：
    1. Dense FAQ / Dense Chunk 负责主排序。
    2. BM25 命中同一个 faq_id 时，只给 Dense 候选加一个很小的 boost。
    3. BM25 独有候选保留为兜底，但按较低权重排在 Dense 候选之后。

    注意：后续 rule reranker 会优先读取 fusion_score。
    因此这里把 Dense 主排序后的分数同时写入 final_score 和 fusion_score，
    避免后续链路退回到旧的 RRF/分数混用逻辑。
    """
    sparse_list = list(sparse_candidates)
    sparse_by_faq = _best_sparse_by_faq(sparse_list)

    merged_by_id: dict[str, RetrievalCandidate] = {}
    boosted_faq_ids: set[str] = set()

    for candidate in dense_candidates:
        bm25_match = sparse_by_faq.get(candidate.faq_id)
        score = candidate.dense_score or 0.0
        sparse_score: Optional[float] = candidate.sparse_score
        sources = list(candidate.sources)
        reasons = list(candidate.rerank_reasons)

        if bm25_match is not None:
            score += same_faq_boost
            sparse_score = bm25_match.sparse_score
            boosted_faq_ids.add(candidate.faq_id)
            sources = _merge_sources(candidate.sources, bm25_match.sources)
            reasons.append(f"bm25_same_faq_boost:+{same_faq_boost:.3f}")

        merged_by_id[candidate.id] = candidate.model_copy(
            update={
                "sparse_score": sparse_score,
                "sources": sources,
                "fusion_score": round(score, 6),
                "final_score": round(score, 6),
                "rerank_reasons": reasons,
            }
        )

    for candidate in sparse_list:
        # 如果这个 FAQ 已经被 Dense 命中，BM25 已经作为 boost 使用；
        # 不再额外放入一个同 FAQ 的稀疏候选，避免 evidence selection 出现重复证据。
        if candidate.faq_id in boosted_faq_ids or candidate.id in merged_by_id:
            continue
        score = sparse_only_weight * (candidate.sparse_score or 0.0)
        merged_by_id[candidate.id] = candidate.model_copy(
            update={
                "fusion_score": round(score, 6),
                "final_score": round(score, 6),
            }
        )

    return sorted(
        merged_by_id.values(),
        key=lambda item: (
            item.final_score or 0.0,
            item.dense_score or 0.0,
            item.sparse_score or 0.0,
        ),
        reverse=True,
    )


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
