"""规则版可解释重排器。"""

from __future__ import annotations

from app.rag.schemas import QueryAnalysis, RetrievalCandidate


def _contains_keyword(candidate: RetrievalCandidate, keyword: str) -> bool:
    # 兜底匹配：有些旧索引或旧数据可能还没有 keywords 字段，
    # 这时仍然可以从分类、标题、正文里判断是否包含关键词。
    haystack = f"{candidate.category} {candidate.question} {candidate.text}".lower()
    return keyword.lower() in haystack


def _matched_keywords(candidate: RetrievalCandidate, keywords: list[str]) -> list[str]:
    """找出 query 关键词中哪些确实命中了当前候选文档。

    优先看离线打标的 document.keywords；如果没有命中，再看原文。
    返回值会写入 RetrievalCandidate.matched_keywords，用于接口和 CLI 排查。
    """
    document_keywords = set(candidate.keywords)
    matched: list[str] = []
    for keyword in keywords:
        if keyword in document_keywords or _contains_keyword(candidate, keyword):
            matched.append(keyword)
    return matched


def rerank_candidates(candidates: list[RetrievalCandidate], analysis: QueryAnalysis) -> list[RetrievalCandidate]:
    """使用可见的特征贡献对合并后的候选结果排序。"""
    ranked: list[RetrievalCandidate] = []
    for candidate in candidates:
        score = 0.0
        reasons: list[str] = []

        if candidate.fusion_score is not None:
            # 正常 RAG 主链路会先经过 RRF fusion。
            # fusion_score 表示候选在多路召回中的综合排名贡献。
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
            # 分类只做 soft boost，不做 hard filter。
            # 这样 query planning 分类误判时，不会直接过滤掉正确 FAQ。
            score += 0.15
            reasons.append("category_match:+0.150")

        overlap = _matched_keywords(candidate, analysis.keywords)
        if overlap:
            # 命中越多 query 关键词，说明候选越贴近用户意图。
            # 上限 0.20 是为了避免关键词数量过多时压过 fusion 主信号。
            contribution = min(0.20, 0.05 * len(overlap))
            score += contribution
            reasons.append(f"keyword_overlap:{','.join(overlap)}:+{contribution:.3f}")

        normalized_query = analysis.normalized_query.lower()
        if normalized_query and normalized_query in candidate.question.lower():
            score += 0.12
            reasons.append("question_exact:+0.120")

        if "bm25" in candidate.sources and ("dense_faq" in candidate.sources or "dense_chunk" in candidate.sources):
            # 同一候选同时被 dense 和 BM25 召回，通常比单路召回更可信。
            score += 0.05
            reasons.append("hybrid_hit:+0.050")

        if candidate.doc_type == "faq":
            score += 0.02
            reasons.append("faq_level:+0.020")

        ranked.append(
            candidate.model_copy(
                update={
                    "final_score": round(score, 6),
                    # 把命中的关键词带出去，方便接口、CLI 和调试页面解释结果。
                    "matched_keywords": overlap,
                    "rerank_reasons": reasons,
                }
            )
        )

    return sorted(ranked, key=lambda item: (item.final_score or 0.0, item.sparse_score or 0.0), reverse=True)
