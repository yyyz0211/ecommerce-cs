"""把用户问题转换成可执行检索计划。"""

from __future__ import annotations

from typing import Optional

from app.rag.planning.analyzer import analyze_query
from app.rag.schemas import RetrievalPlan


def plan_query(query: str, *, category: Optional[str] = None) -> RetrievalPlan:
    """生成检索计划，作为后续召回、融合和重排的统一输入。"""
    analysis = analyze_query(query, category=category)
    retrieval_query = analysis.rewrite_query or analysis.normalized_query or analysis.raw_query
    filters = {"category": analysis.category} if analysis.category else {}
    return RetrievalPlan(
        **analysis.model_dump(),
        retrieval_queries=[retrieval_query],
        filters=filters,
    )
