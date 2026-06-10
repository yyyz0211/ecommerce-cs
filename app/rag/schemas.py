"""RAG 数据契约。"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class RAGDocument(BaseModel):
    """存入检索索引的 FAQ 级别文档或 chunk。"""

    id: str
    faq_id: str
    doc_type: str = Field(default="chunk", description="FAQ 文档或 chunk")
    chunk_index: int = 0
    chunk_count: int = 1
    source: str = "京东帮助中心"
    category: str
    question: str
    text: str
    url: str
    section_title: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    keyword_version: Optional[str] = None


class RAGMatch(BaseModel):
    """原始召回通道返回的 FAQ 级别文档或 chunk。"""

    id: str
    faq_id: str
    doc_type: str = "chunk"
    chunk_index: int = 0
    chunk_count: int = 1
    category: str
    question: str
    text: str
    url: str
    source: str = "京东帮助中心"
    section_title: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    keyword_version: Optional[str] = None
    distance: Optional[float] = None
    score: Optional[float] = Field(default=None, description="由 distance 换算出的展示分数。")
    retrieval_source: Optional[str] = Field(default=None, description="召回来源：dense_faq、dense_chunk 或 bm25。")


class RAGSearchResult(BaseModel):
    """服务层稳定返回的检索结果。"""

    query: str
    matches: list[RAGMatch]


class QueryAnalysis(BaseModel):
    """检索前使用的归一化 query 信息。"""

    raw_query: str
    normalized_query: str
    category: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    needs_business_tool: bool = False
    rewrite_query: Optional[str] = None


class RetrievalPlan(QueryAnalysis):
    """Query Planner 产出的检索计划。"""

    retrieval_queries: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)

    @property
    def primary_query(self) -> str:
        """返回后续召回阶段优先使用的检索文本。"""
        if self.rewrite_query:
            return self.rewrite_query
        if self.retrieval_queries:
            return self.retrieval_queries[0]
        return self.normalized_query or self.raw_query


class RetrievalCandidate(BaseModel):
    """合并后的候选结果，包含一个或多个召回通道的分数。"""

    id: str
    faq_id: str
    doc_type: str = "chunk"
    chunk_index: int = 0
    chunk_count: int = 1
    source: str = "京东帮助中心"
    category: str
    question: str
    text: str
    url: str
    section_title: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    keyword_version: Optional[str] = None
    matched_keywords: list[str] = Field(default_factory=list)
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    fusion_score: Optional[float] = Field(default=None, description="RRF 融合后的归一化分数。")
    final_score: Optional[float] = None
    sources: list[str] = Field(default_factory=list)
    rerank_reasons: list[str] = Field(default_factory=list)


class ContextSelection(BaseModel):
    """为答案生成选出的 grounding 上下文。"""

    query: str
    contexts: list[RetrievalCandidate]
    coverage: str
    total_chars: int


class RetrievalTrace(BaseModel):
    """用于 CLI 排查和调试的完整检索链路 trace。"""

    query: str
    analysis: RetrievalPlan
    dense_faq: list[RetrievalCandidate] = Field(default_factory=list)
    dense_chunk: list[RetrievalCandidate] = Field(default_factory=list)
    sparse: list[RetrievalCandidate] = Field(default_factory=list)
    merged: list[RetrievalCandidate] = Field(default_factory=list)
    reranked: list[RetrievalCandidate] = Field(default_factory=list)
    selection: ContextSelection
