"""规则版可解释重排器。"""

from __future__ import annotations

from app.rag.schemas import QueryAnalysis, RetrievalCandidate


def _contains_keyword(candidate: RetrievalCandidate, keyword: str) -> bool:
    haystack = f"{candidate.category} {candidate.question} {candidate.text}".lower()
    return keyword.lower() in haystack


def rerank_candidates(candidates: list[RetrievalCandidate], analysis: QueryAnalysis) -> list[RetrievalCandidate]:
    """使用可见的特征贡献对合并后的候选结果排序。"""
    ranked: list[RetrievalCandidate] = []
    for candidate in candidates:
        score = 0.0
        reasons: list[str] = []

        if candidate.fusion_score is not None:
            contribution = 0.35 * candidate.fusion_score
            score += contribution
            reasons.append(f"rrf_fusion:{contribution:.3f}")
        else:
            # 单元测试或单路调用可能没有经过 fusion，保留旧分数作为兜底。
            if candidate.dense_score is not None:
                contribution = 0.35 * candidate.dense_score
                score += contribution
                reasons.append(f"dense_score:{contribution:.3f}")

            if candidate.sparse_score is not None:
                contribution = 0.25 * candidate.sparse_score
                score += contribution
                reasons.append(f"bm25_score:{contribution:.3f}")

        if analysis.category and candidate.category == analysis.category:
            score += 0.15
            reasons.append("category_match:+0.150")

        overlap = [keyword for keyword in analysis.keywords if _contains_keyword(candidate, keyword)]
        if overlap:
            contribution = min(0.20, 0.05 * len(overlap))
            score += contribution
            reasons.append(f"keyword_overlap:{','.join(overlap)}:+{contribution:.3f}")

        normalized_query = analysis.normalized_query.lower()
        if normalized_query and normalized_query in candidate.question.lower():
            score += 0.12
            reasons.append("question_exact:+0.120")

        if "bm25" in candidate.sources and ("dense_faq" in candidate.sources or "dense_chunk" in candidate.sources):
            score += 0.05
            reasons.append("hybrid_hit:+0.050")

        if candidate.doc_type == "faq":
            score += 0.02
            reasons.append("faq_level:+0.020")

        ranked.append(candidate.model_copy(update={"final_score": round(score, 6), "rerank_reasons": reasons}))

    return sorted(ranked, key=lambda item: (item.final_score or 0.0, item.sparse_score or 0.0), reverse=True)
