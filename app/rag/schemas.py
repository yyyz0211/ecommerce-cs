"""RAG data contracts."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RAGDocument(BaseModel):
    """A FAQ-level document or chunk stored in retrieval indexes."""

    id: str
    faq_id: str
    doc_type: str = Field(default="chunk", description="faq or chunk")
    chunk_index: int = 0
    chunk_count: int = 1
    source: str = "京东帮助中心"
    category: str
    question: str
    text: str
    url: str
    section_title: Optional[str] = None


class RAGMatch(BaseModel):
    """A retrieved FAQ-level document or chunk from a raw recall channel."""

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
    distance: Optional[float] = None
    score: Optional[float] = Field(default=None, description="Convenience score derived from distance.")
    retrieval_source: Optional[str] = Field(default=None, description="dense_faq, dense_chunk, or bm25.")


class RAGSearchResult(BaseModel):
    """Stable service-level search result."""

    query: str
    matches: list[RAGMatch]


class QueryAnalysis(BaseModel):
    """Normalized query information used before retrieval."""

    raw_query: str
    normalized_query: str
    category: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    needs_business_tool: bool = False
    rewrite_query: Optional[str] = None


class RetrievalCandidate(BaseModel):
    """Merged candidate with scores from one or more recall channels."""

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
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    final_score: Optional[float] = None
    sources: list[str] = Field(default_factory=list)
    rerank_reasons: list[str] = Field(default_factory=list)


class ContextSelection(BaseModel):
    """Grounding contexts selected for answer generation."""

    query: str
    contexts: list[RetrievalCandidate]
    coverage: str
    total_chars: int


class RetrievalTrace(BaseModel):
    """Full pipeline trace for CLI inspection and debugging."""

    query: str
    analysis: QueryAnalysis
    dense_faq: list[RetrievalCandidate] = Field(default_factory=list)
    dense_chunk: list[RetrievalCandidate] = Field(default_factory=list)
    sparse: list[RetrievalCandidate] = Field(default_factory=list)
    merged: list[RetrievalCandidate] = Field(default_factory=list)
    reranked: list[RetrievalCandidate] = Field(default_factory=list)
    selection: ContextSelection
