"""评测京东 FAQ RAG 从关键词基线到当前完整系统的效果。

示例：
    python3 scripts/rag_eval.py
    python3 scripts/rag_eval.py --limit 5

输出：
    data/rag_eval/production_like_eval_report.md
    data/rag_eval/production_like_eval_results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.rag.indexing.embeddings import embed_query, embed_texts
from app.rag.indexing.keyword_store import KeywordSearchIndex, tokenize, tokenize_document
from app.rag.indexing.loader import load_documents, load_faq_documents
from app.rag.indexing.vector_store import query_documents
from app.rag.evidence.selector import select_evidence
from app.rag.planning.planner import plan_query
from app.rag.reranking.rule import rerank_candidates
from app.rag.retrieval.dense import candidate_from_match
from app.rag.retrieval.fusion import merge_candidates, merge_candidates_dense_primary
from app.rag.retrieval.hybrid import retrieve_candidates
from app.rag.schemas import RAGDocument, RetrievalCandidate


DEFAULT_PRODUCTION_LIKE_CASES_PATH = ROOT_DIR / "data" / "rag_eval" / "production_like_cases.jsonl"
DEFAULT_PRODUCTION_LIKE_REPORT_PATH = ROOT_DIR / "data" / "rag_eval" / "production_like_eval_report.md"
DEFAULT_PRODUCTION_LIKE_JSON_PATH = ROOT_DIR / "data" / "rag_eval" / "production_like_eval_results.json"
DEFAULT_FAQ_PATH = ROOT_DIR / "data" / "jd_faq_clean.jsonl"
DEFAULT_CHUNK_PATH = ROOT_DIR / "data" / "jd_faq_chunks.jsonl"


@dataclass(frozen=True)
class EvalVersion:
    key: str
    label: str
    description: str


EVAL_VERSIONS = [
    # 这些版本用于做消融实验：不是线上都有独立实现，而是逐步打开能力。
    # 通过 V0 到 V7 的指标变化，可以判断 BM25、Dense、Fusion、Rerank 各自是否有效。
    EvalVersion("rag_v0_keyword", "RAG-V0 关键词基线", "字符串关键词重叠排序，不使用 BM25、向量、融合或重排。"),
    EvalVersion("rag_v1_bm25_faq", "RAG-V1 BM25 FAQ", "只在 FAQ 级别文档上做 BM25 检索。"),
    EvalVersion("rag_v2_dense_chunk", "RAG-V2 Dense Chunk", "只在 chunk 向量集合上做语义召回。"),
    EvalVersion("rag_v3_dense_faq_chunk", "RAG-V3 Dense FAQ + Dense Chunk", "同时召回 FAQ 向量和 chunk 向量，按向量分数直接排序。"),
    EvalVersion("rag_v4_dense_bm25_hybrid", "RAG-V4 Dense + BM25 混合检索", "Dense FAQ、Dense Chunk、BM25 多路结果直接拼接，并按通道分数排序。"),
    EvalVersion("rag_v5_hybrid_fusion", "RAG-V5 混合检索 + Fusion", "在 V4 基础上按文档 ID 去重，合并来源和通道分数。"),
    EvalVersion("rag_v5a_weighted_rrf", "RAG-V5a 加权 RRF", "Dense 通道权重保持 1.0，BM25 通道降权到 0.5，观察是否减少 BM25 噪声。"),
    EvalVersion("rag_v5b_bm25_top5_rrf", "RAG-V5b BM25 Top5 + RRF", "只取 BM25 前 5 个候选参与 RRF，减少稀疏召回噪声进入融合。"),
    EvalVersion("rag_v5c_dense_bm25_boost", "RAG-V5c Dense 主排序 + BM25 Boost", "Dense 负责主排序，BM25 只给同 FAQ 命中的 Dense 候选轻量加分。"),
    EvalVersion("rag_v5d_dense_bm25_light_boost", "RAG-V5d Dense 主排序 + BM25 轻量 Boost", "Dense 负责主排序，BM25 同 FAQ 命中只加 0.02，进一步降低噪声。"),
    EvalVersion("rag_v6_hybrid_fusion_rule_rerank", "RAG-V6 混合检索 + Fusion + Rule Rerank", "在 V5 基础上使用分类、关键词、通道命中等可解释规则重排。"),
    EvalVersion("rag_v7_current", "RAG-V7 当前完整系统", "等价执行当前 run_rag_pipeline 的各组件，包含 query planning、混合检索、fusion、rule rerank 和 evidence selection。"),
]


@dataclass
class EvalCase:
    id: str
    query: str
    category: str
    expected_faq_ids: list[str]
    expected_titles: list[str]
    difficulty: str
    tags: list[str]
    notes: str = ""
    source: str = "dev"
    should_use_rag: bool = True
    should_use_business_tool: bool = False


@dataclass
class CaseMetrics:
    hit_at_1: int
    hit_at_3: int
    hit_at_5: int
    mrr: float
    category_hit_at_1: int
    first_hit_rank: Optional[int]
    result_count: int


@dataclass
class CaseEvalResult:
    case_id: str
    query: str
    category: str
    expected_faq_ids: list[str]
    expected_titles: list[str]
    difficulty: str
    tags: list[str]
    source: str
    should_use_rag: bool
    should_use_business_tool: bool
    metrics: CaseMetrics
    latency_ms: float
    results: list[dict[str, Any]]


@dataclass
class VersionEvalResult:
    version: EvalVersion
    case_results: list[CaseEvalResult]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评测京东 FAQ RAG 各版本效果。")
    parser.add_argument("--suite", choices=("production_like",), default="production_like", help="评测集类型。")
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--faq-input", type=Path, default=DEFAULT_FAQ_PATH)
    parser.add_argument("--chunks-input", type=Path, default=DEFAULT_CHUNK_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--dense-top-k", type=int, default=20)
    parser.add_argument("--sparse-top-k", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None, help="只评测前 N 条 case，便于调试。")
    parser.add_argument("--max-context-chars", type=int, default=2400)
    parser.add_argument("--embedding-batch-size", type=int, default=10, help="批量生成 query embedding 的批大小。阿里云兼容接口单批最大为 10。")
    return parser.parse_args()


def apply_suite_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """根据评测集类型填充默认输入输出路径，显式传入的路径优先生效。"""
    default_cases = DEFAULT_PRODUCTION_LIKE_CASES_PATH
    default_output = DEFAULT_PRODUCTION_LIKE_REPORT_PATH
    default_json_output = DEFAULT_PRODUCTION_LIKE_JSON_PATH

    if args.cases is None:
        args.cases = default_cases
    if args.output is None:
        args.output = default_output
    if args.json_output is None:
        args.json_output = default_json_output
    return args


def load_eval_cases(path: Path, *, limit: Optional[int] = None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                cases.append(EvalCase(**payload))
            except Exception as exc:
                raise ValueError(f"评测集 JSONL 行无效: {path}:{line_no}: {exc}") from exc
            if limit is not None and len(cases) >= limit:
                break
    return cases


def document_to_candidate(
    document: RAGDocument,
    *,
    sparse_score: Optional[float] = None,
    dense_score: Optional[float] = None,
    source: str,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        id=document.id,
        faq_id=document.faq_id,
        doc_type=document.doc_type,
        chunk_index=document.chunk_index,
        chunk_count=document.chunk_count,
        source=document.source,
        category=document.category,
        question=document.question,
        text=document.text,
        url=document.url,
        section_title=document.section_title,
        dense_score=dense_score,
        sparse_score=sparse_score,
        sources=[source],
    )


def keyword_overlap_score(query: str, candidate: RetrievalCandidate) -> float:
    """V0 使用的简单关键词重叠得分。

    这是最低成本基线：不调用 embedding，不建 BM25，只看 query 和 FAQ 字面 token 是否重叠。
    如果复杂系统还不如它，通常说明融合、重排或 query planning 有回归。
    """
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    title_tokens = set(tokenize(candidate.question))
    text_tokens = set(tokenize(candidate.text))
    category_tokens = set(tokenize(candidate.category))
    title_hits = len(query_tokens & title_tokens)
    text_hits = len(query_tokens & text_tokens)
    category_hits = len(query_tokens & category_tokens)
    return title_hits * 2.0 + text_hits * 1.0 + category_hits * 0.5


def run_keyword_baseline(query: str, faq_documents: list[RAGDocument], *, top_k: int) -> list[RetrievalCandidate]:
    scored: list[RetrievalCandidate] = []
    for document in faq_documents:
        candidate = document_to_candidate(document, source="keyword")
        score = keyword_overlap_score(query, candidate)
        if score <= 0:
            continue
        scored.append(candidate.model_copy(update={"sparse_score": score, "final_score": score}))
    return sorted(scored, key=lambda item: item.final_score or 0.0, reverse=True)[:top_k]


def build_keyword_search_index(documents: list[RAGDocument]) -> KeywordSearchIndex:
    # 评测时直接从传入文档构建 BM25，避免读取磁盘上的旧 pkl。
    # 这样结果严格对应 --faq-input / --chunks-input 指定的数据。
    tokenized_corpus = [tokenize_document(doc) for doc in documents]
    return KeywordSearchIndex(documents, tokenized_corpus)


def run_bm25(query: str, index: KeywordSearchIndex, *, top_k: int, source: str = "bm25") -> list[RetrievalCandidate]:
    # source 会被 fusion/rerank 用来判断候选来自哪一路召回。
    candidates = index.search(query, top_k=top_k)
    return [candidate.model_copy(update={"sources": [source]}) for candidate in candidates]


def query_dense_collection(
    query_embedding: list[float],
    *,
    collection_name: str,
    source: str,
    top_k: int,
) -> list[RetrievalCandidate]:
    matches = query_documents(query_embedding, top_k=top_k, collection_name=collection_name)
    return [candidate_from_match(match, source) for match in matches]


def rank_candidates_by_dense(candidates: Iterable[RetrievalCandidate]) -> list[RetrievalCandidate]:
    return sorted(candidates, key=lambda item: item.dense_score or 0.0, reverse=True)


def rank_candidates_for_v4(candidates: Iterable[RetrievalCandidate]) -> list[RetrievalCandidate]:
    """V4 对未融合的多路召回结果做朴素排序。

    这里还没有 RRF，只是把 dense 和 BM25 候选拼起来按通道分数排序。
    如果 V4 明显差于 V5，通常说明“直接混用不同通道分数”不可靠。
    """
    return sorted(
        candidates,
        key=lambda item: (
            max(item.dense_score or 0.0, item.sparse_score or 0.0),
            item.sparse_score or 0.0,
            item.dense_score or 0.0,
        ),
        reverse=True,
    )


def fusion_score(candidate: RetrievalCandidate) -> float:
    if candidate.fusion_score is not None:
        return candidate.fusion_score
    dense = candidate.dense_score or 0.0
    sparse = candidate.sparse_score or 0.0
    score = 0.5 * dense + 0.5 * sparse
    if dense > 0 and sparse > 0:
        score += 0.05
    return score


def rank_fused_candidates(candidates: Iterable[RetrievalCandidate]) -> list[RetrievalCandidate]:
    return sorted(candidates, key=fusion_score, reverse=True)


def merge_candidates_weighted_rrf(
    *weighted_groups: tuple[Iterable[RetrievalCandidate], float],
    rrf_k: int = 60,
) -> list[RetrievalCandidate]:
    """评测用加权 RRF。

    标准 RRF 默认每个召回通道权重相同。
    这里允许降低 BM25 权重，用来验证“BM25 是补充信号还是噪声源”。
    """
    merged: dict[str, RetrievalCandidate] = {}
    rrf_scores: dict[str, float] = {}

    for group, weight in weighted_groups:
        for rank, candidate in enumerate(list(group), start=1):
            rrf_scores[candidate.id] = rrf_scores.get(candidate.id, 0.0) + weight / (rrf_k + rank)
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
    return rank_fused_candidates(fused)


def rank_dense_with_bm25_boost(
    dense_candidates: Iterable[RetrievalCandidate],
    sparse_candidates: Iterable[RetrievalCandidate],
    *,
    same_faq_boost: float = 0.05,
    sparse_only_weight: float = 0.2,
) -> list[RetrievalCandidate]:
    """Dense 主排序实验。

    Dense 当前真实指标最好，因此这里让 Dense 保持主排序。
    BM25 只做两件事：
    1. 如果同一个 faq_id 也被 BM25 命中，给 Dense 候选一个小 boost。
    2. BM25 独有结果保留，但按较低权重排在 Dense 候选后面。
    """
    sparse_by_faq: dict[str, RetrievalCandidate] = {}
    for candidate in sparse_candidates:
        current = sparse_by_faq.get(candidate.faq_id)
        if current is None or (candidate.sparse_score or 0.0) > (current.sparse_score or 0.0):
            sparse_by_faq[candidate.faq_id] = candidate

    ranked_by_id: dict[str, RetrievalCandidate] = {}
    for candidate in dense_candidates:
        bm25_match = sparse_by_faq.get(candidate.faq_id)
        score = candidate.dense_score or 0.0
        sources = list(candidate.sources)
        reasons: list[str] = []
        sparse_score = candidate.sparse_score
        if bm25_match is not None:
            score += same_faq_boost
            sparse_score = bm25_match.sparse_score
            reasons.append(f"bm25_same_faq_boost:+{same_faq_boost:.3f}")
            for source in bm25_match.sources:
                if source not in sources:
                    sources.append(source)
        ranked_by_id[candidate.id] = candidate.model_copy(
            update={
                "sparse_score": sparse_score,
                "final_score": round(score, 6),
                "sources": sources,
                "rerank_reasons": reasons,
            }
        )

    for candidate in sparse_candidates:
        if candidate.id in ranked_by_id:
            continue
        score = sparse_only_weight * (candidate.sparse_score or 0.0)
        ranked_by_id[candidate.id] = candidate.model_copy(update={"final_score": round(score, 6)})

    return sorted(ranked_by_id.values(), key=lambda item: item.final_score or 0.0, reverse=True)


def candidate_to_result(candidate: RetrievalCandidate, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "id": candidate.id,
        "faq_id": candidate.faq_id,
        "doc_type": candidate.doc_type,
        "category": candidate.category,
        "title": candidate.question,
        "dense_score": candidate.dense_score,
        "sparse_score": candidate.sparse_score,
        "fusion_score": candidate.fusion_score,
        "final_score": candidate.final_score,
        "sources": candidate.sources,
        "reasons": candidate.rerank_reasons,
        "url": candidate.url,
    }


def compute_case_metrics(
    *,
    expected_faq_ids: set[str],
    expected_category: str,
    candidates: list[RetrievalCandidate],
) -> CaseMetrics:
    first_hit_rank: Optional[int] = None
    for index, candidate in enumerate(candidates, start=1):
        if candidate.faq_id in expected_faq_ids:
            first_hit_rank = index
            break

    return CaseMetrics(
        hit_at_1=1 if first_hit_rank == 1 else 0,
        hit_at_3=1 if first_hit_rank is not None and first_hit_rank <= 3 else 0,
        hit_at_5=1 if first_hit_rank is not None and first_hit_rank <= 5 else 0,
        mrr=0.0 if first_hit_rank is None else 1.0 / first_hit_rank,
        category_hit_at_1=1 if candidates and candidates[0].category == expected_category else 0,
        first_hit_rank=first_hit_rank,
        result_count=len(candidates),
    )


class RagEvaluator:
    def __init__(
        self,
        *,
        faq_documents: list[RAGDocument],
        chunk_documents: list[RAGDocument],
        top_k: int,
        dense_top_k: int,
        sparse_top_k: int,
        max_context_chars: int,
    ):
        self.faq_documents = faq_documents
        self.chunk_documents = chunk_documents
        self.top_k = top_k
        self.dense_top_k = dense_top_k
        self.sparse_top_k = sparse_top_k
        self.max_context_chars = max_context_chars
        self.bm25_faq = build_keyword_search_index(faq_documents)
        self.bm25_all = build_keyword_search_index([*faq_documents, *chunk_documents])
        self.embedding_cache: dict[str, list[float]] = {}

    def warm_embedding_cache(self, queries: list[str], *, batch_size: int) -> None:
        """批量预热 query 向量，降低评测脚本的网络请求次数。"""
        batch_size = max(1, batch_size)
        missing = list(dict.fromkeys(query for query in queries if query and query not in self.embedding_cache))
        for start in range(0, len(missing), batch_size):
            batch = missing[start : start + batch_size]
            vectors = embed_texts(batch)
            if len(vectors) != len(batch):
                raise RuntimeError(f"embedding 返回数量不一致: inputs={len(batch)} vectors={len(vectors)}")
            for query, vector in zip(batch, vectors):
                self.embedding_cache[query] = vector

    async def embed_for_eval(self, query: str) -> list[float]:
        """缓存评测用 query 向量，避免 V2-V6 对同一问题重复请求 embedding API。"""
        cached = self.embedding_cache.get(query)
        if cached is not None:
            return cached
        embedding = await embed_query(query)
        self.embedding_cache[query] = embedding
        return embedding

    async def run_version(self, version_key: str, case: EvalCase) -> list[RetrievalCandidate]:
        if version_key == "rag_v0_keyword":
            return run_keyword_baseline(case.query, self.faq_documents, top_k=self.top_k)

        if version_key == "rag_v1_bm25_faq":
            return run_bm25(case.query, self.bm25_faq, top_k=self.top_k, source="bm25_faq")

        if version_key in {
            "rag_v2_dense_chunk",
            "rag_v3_dense_faq_chunk",
            "rag_v4_dense_bm25_hybrid",
            "rag_v5_hybrid_fusion",
            "rag_v5a_weighted_rrf",
            "rag_v5b_bm25_top5_rrf",
            "rag_v5c_dense_bm25_boost",
            "rag_v5d_dense_bm25_light_boost",
            "rag_v6_hybrid_fusion_rule_rerank",
        }:
            query_embedding = await self.embed_for_eval(case.query)
            dense_faq: list[RetrievalCandidate] = []
            dense_chunk: list[RetrievalCandidate] = []

            if version_key != "rag_v2_dense_chunk":
                dense_faq = query_dense_collection(
                    query_embedding,
                    collection_name=settings.CHROMA_DOC_COLLECTION,
                    source="dense_faq",
                    top_k=self.dense_top_k,
                )
            dense_chunk = query_dense_collection(
                query_embedding,
                collection_name=settings.CHROMA_CHUNK_COLLECTION,
                source="dense_chunk",
                top_k=self.dense_top_k,
            )

            if version_key == "rag_v2_dense_chunk":
                return rank_candidates_by_dense(dense_chunk)[: self.top_k]

            if version_key == "rag_v3_dense_faq_chunk":
                return rank_candidates_by_dense([*dense_faq, *dense_chunk])[: self.top_k]

            sparse = run_bm25(case.query, self.bm25_all, top_k=self.sparse_top_k, source="bm25")

            if version_key == "rag_v4_dense_bm25_hybrid":
                return rank_candidates_for_v4([*dense_faq, *dense_chunk, *sparse])[: self.top_k]

            merged = merge_candidates(dense_faq, dense_chunk, sparse)
            if version_key == "rag_v5_hybrid_fusion":
                return rank_fused_candidates(merged)[: self.top_k]

            if version_key == "rag_v5a_weighted_rrf":
                weighted = merge_candidates_weighted_rrf(
                    (dense_faq, 1.0),
                    (dense_chunk, 1.0),
                    (sparse, 0.5),
                )
                return weighted[: self.top_k]

            if version_key == "rag_v5b_bm25_top5_rrf":
                sparse_top5 = sparse[:5]
                limited = merge_candidates(dense_faq, dense_chunk, sparse_top5)
                return rank_fused_candidates(limited)[: self.top_k]

            if version_key == "rag_v5c_dense_bm25_boost":
                dense_ranked = rank_candidates_by_dense([*dense_faq, *dense_chunk])
                boosted = rank_dense_with_bm25_boost(dense_ranked, sparse)
                return boosted[: self.top_k]

            if version_key == "rag_v5d_dense_bm25_light_boost":
                dense_ranked = rank_candidates_by_dense([*dense_faq, *dense_chunk])
                boosted = rank_dense_with_bm25_boost(dense_ranked, sparse, same_faq_boost=0.02)
                return boosted[: self.top_k]

            plan = plan_query(case.query)
            return rerank_candidates(merged, plan)[: self.top_k]

        if version_key == "rag_v7_current":
            plan = plan_query(case.query)
            query_embedding = await self.embed_for_eval(plan.primary_query)
            channels = retrieve_candidates(
                plan,
                query_embedding,
                dense_top_k=self.dense_top_k,
                sparse_top_k=self.sparse_top_k,
            )
            # V7 需要和生产 pipeline 保持一致：
            # Dense 负责主排序，BM25 只对同 FAQ 命中的候选做 0.02 轻量 boost。
            merged = merge_candidates_dense_primary(
                [*channels.dense_faq, *channels.dense_chunk],
                channels.sparse,
                same_faq_boost=0.02,
            )
            reranked = rerank_candidates(merged, plan)
            selection = select_evidence(
                reranked,
                query=case.query,
                top_k=self.top_k,
                max_chars=self.max_context_chars,
            )
            return selection.contexts

        raise ValueError(f"未知评测版本: {version_key}")

    async def evaluate_version(self, version: EvalVersion, cases: list[EvalCase]) -> VersionEvalResult:
        results: list[CaseEvalResult] = []
        for case in cases:
            started = time.perf_counter()
            candidates = await self.run_version(version.key, case)
            latency_ms = (time.perf_counter() - started) * 1000
            metrics = compute_case_metrics(
                expected_faq_ids=set(case.expected_faq_ids),
                expected_category=case.category,
                candidates=candidates,
            )
            results.append(
                CaseEvalResult(
                    case_id=case.id,
                    query=case.query,
                    category=case.category,
                    expected_faq_ids=case.expected_faq_ids,
                    expected_titles=case.expected_titles,
                    difficulty=case.difficulty,
                    tags=case.tags,
                    source=case.source,
                    should_use_rag=case.should_use_rag,
                    should_use_business_tool=case.should_use_business_tool,
                    metrics=metrics,
                    latency_ms=latency_ms,
                    results=[candidate_to_result(candidate, index) for index, candidate in enumerate(candidates, start=1)],
                )
            )
        return VersionEvalResult(version=version, case_results=results)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def aggregate_version(result: VersionEvalResult) -> dict[str, Any]:
    """汇总单个版本的整体指标。

    Recall@K：期望 FAQ 是否出现在前 K 条结果中。
    MRR：第一个正确答案越靠前，分数越高。
    category_accuracy_at_1：首条结果分类是否与标注分类一致。
    """
    total = len(result.case_results)
    if total == 0:
        return {
            "total": 0,
            "recall_at_1": 0.0,
            "recall_at_3": 0.0,
            "recall_at_5": 0.0,
            "mrr": 0.0,
            "category_accuracy_at_1": 0.0,
            "no_result_rate": 0.0,
            "avg_latency_ms": 0.0,
        }
    metrics = [item.metrics for item in result.case_results]
    return {
        "total": total,
        "recall_at_1": sum(item.hit_at_1 for item in metrics) / total,
        "recall_at_3": sum(item.hit_at_3 for item in metrics) / total,
        "recall_at_5": sum(item.hit_at_5 for item in metrics) / total,
        "mrr": sum(item.mrr for item in metrics) / total,
        "category_accuracy_at_1": sum(item.category_hit_at_1 for item in metrics) / total,
        "no_result_rate": sum(1 for item in metrics if item.result_count == 0) / total,
        "avg_latency_ms": sum(item.latency_ms for item in result.case_results) / total,
    }


def aggregate_by_category(result: VersionEvalResult) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[CaseEvalResult]] = defaultdict(list)
    for item in result.case_results:
        groups[item.category].append(item)

    aggregated: dict[str, dict[str, Any]] = {}
    for category, items in sorted(groups.items()):
        total = len(items)
        aggregated[category] = {
            "total": total,
            "recall_at_1": sum(item.metrics.hit_at_1 for item in items) / total,
            "recall_at_3": sum(item.metrics.hit_at_3 for item in items) / total,
            "mrr": sum(item.metrics.mrr for item in items) / total,
        }
    return aggregated


def markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    return "\n".join(lines)


def summarize_cases(cases: list[EvalCase]) -> dict[str, Any]:
    return {
        "total": len(cases),
        "by_category": dict(Counter(case.category for case in cases)),
        "by_difficulty": dict(Counter(case.difficulty for case in cases)),
        "by_source": dict(Counter(case.source for case in cases)),
        "should_use_business_tool": sum(1 for case in cases if case.should_use_business_tool),
    }


def build_report(
    *,
    cases: list[EvalCase],
    version_results: list[VersionEvalResult],
    faq_count: int,
    chunk_count: int,
    dense_doc_count: Optional[int],
    dense_chunk_count: Optional[int],
    generated_at: str,
    suite: str,
    json_output: Path,
) -> str:
    case_summary = summarize_cases(cases)
    aggregates = {result.version.key: aggregate_version(result) for result in version_results}

    lines: list[str] = [
        "# 京东 FAQ RAG 版本评测报告",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 评测口径",
        "",
        "所有版本使用同一份评测集。V0 到 V7 是功能消融版本，不代表 Git 历史版本；它们用于观察每一步能力引入后的指标变化。",
        "",
        "为降低 API 请求次数，同一个 query 文本的 embedding 会在评测脚本内复用。该缓存不改变召回结果，只影响脚本执行耗时。因此报告中的耗时用于观察评测运行成本，不应直接等同于线上端到端延迟。",
        "",
        markdown_table(
            ["版本", "定义"],
            [[version.label, version.description] for version in EVAL_VERSIONS],
        ),
        "",
        "## 数据与索引",
        "",
        markdown_table(
            ["项目", "数量"],
            [
                ["评测 suite", suite],
                ["评测 case", case_summary["total"]],
                ["实际入库 FAQ 文档", faq_count],
                ["Chunk 文档", chunk_count],
                ["Chroma FAQ 向量", dense_doc_count if dense_doc_count is not None else "读取失败"],
                ["Chroma Chunk 向量", dense_chunk_count if dense_chunk_count is not None else "读取失败"],
                ["应走业务工具 case", case_summary["should_use_business_tool"]],
            ],
        ),
        "",
        "### 评测集分布",
        "",
        markdown_table(["分类", "case 数"], sorted(case_summary["by_category"].items())),
        "",
        markdown_table(["难度", "case 数"], sorted(case_summary["by_difficulty"].items())),
        "",
        markdown_table(["来源", "case 数"], sorted(case_summary["by_source"].items())),
        "",
        "## 总体结果",
        "",
        markdown_table(
            ["版本", "Recall@1", "Recall@3", "Recall@5", "MRR", "Category@1", "No Result", "Avg Eval Time"],
            [
                [
                    next(version.label for version in EVAL_VERSIONS if version.key == key),
                    pct(value["recall_at_1"]),
                    pct(value["recall_at_3"]),
                    pct(value["recall_at_5"]),
                    f"{value['mrr']:.3f}",
                    pct(value["category_accuracy_at_1"]),
                    pct(value["no_result_rate"]),
                    f"{value['avg_latency_ms']:.1f} ms",
                ]
                for key, value in aggregates.items()
            ],
        ),
        "",
        "## 相邻版本变化",
        "",
    ]

    delta_rows = []
    previous_key: Optional[str] = None
    for version in EVAL_VERSIONS:
        if previous_key is None:
            delta_rows.append([version.label, "-", "-", "-"])
            previous_key = version.key
            continue
        current = aggregates[version.key]
        previous = aggregates[previous_key]
        delta_rows.append(
            [
                version.label,
                f"{(current['recall_at_1'] - previous['recall_at_1']) * 100:+.1f} pp",
                f"{(current['recall_at_3'] - previous['recall_at_3']) * 100:+.1f} pp",
                f"{current['mrr'] - previous['mrr']:+.3f}",
            ]
        )
        previous_key = version.key

    lines.extend(
        [
            markdown_table(["版本", "Recall@1 变化", "Recall@3 变化", "MRR 变化"], delta_rows),
            "",
            "## 分分类结果",
            "",
        ]
    )

    for result in version_results:
        lines.extend(
            [
                f"### {result.version.label}",
                "",
                markdown_table(
                    ["分类", "case 数", "Recall@1", "Recall@3", "MRR"],
                    [
                        [category, value["total"], pct(value["recall_at_1"]), pct(value["recall_at_3"]), f"{value['mrr']:.3f}"]
                        for category, value in aggregate_by_category(result).items()
                    ],
                ),
                "",
            ]
        )

    lines.extend(["## 当前完整系统未命中样例", ""])
    current = version_results[-1]
    misses = [item for item in current.case_results if item.metrics.hit_at_3 == 0]
    if not misses:
        lines.append("RAG-V7 在 Recall@3 口径下没有未命中样例。")
    else:
        lines.append(
            markdown_table(
                ["case", "query", "期望 FAQ", "首条结果", "首条分类"],
                [
                    [
                        item.case_id,
                        item.query,
                        "；".join(item.expected_titles),
                        item.results[0]["title"] if item.results else "无结果",
                        item.results[0]["category"] if item.results else "-",
                    ]
                    for item in misses
                ],
            )
        )

    try:
        json_output_display = json_output.resolve().relative_to(ROOT_DIR)
    except ValueError:
        json_output_display = json_output

    lines.extend(
        [
            "",
            "## 复现命令",
            "",
            "```bash",
            f"python3 scripts/rag_eval.py --suite {suite}",
            "```",
            "",
            f"机器可读原始结果保存在 `{json_output_display}`。",
        ]
    )
    return "\n".join(lines) + "\n"


def count_chroma_collection(collection_name: str) -> Optional[int]:
    try:
        import chromadb

        client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        return client.get_collection(collection_name).count()
    except Exception:
        return None


async def main_async() -> None:
    args = apply_suite_defaults(parse_args())
    cases = load_eval_cases(args.cases, limit=args.limit)
    faq_documents = load_faq_documents(args.faq_input)
    chunk_documents = load_documents(args.chunks_input)
    evaluator = RagEvaluator(
        faq_documents=faq_documents,
        chunk_documents=chunk_documents,
        top_k=args.top_k,
        dense_top_k=args.dense_top_k,
        sparse_top_k=args.sparse_top_k,
        max_context_chars=args.max_context_chars,
    )
    tokenize("warmup 生鲜 拒收 退货 发票")
    embedding_queries: list[str] = []
    for case in cases:
        embedding_queries.append(case.query)
        embedding_queries.append(plan_query(case.query).primary_query)
    evaluator.warm_embedding_cache(embedding_queries, batch_size=args.embedding_batch_size)

    version_results: list[VersionEvalResult] = []
    for version in EVAL_VERSIONS:
        print(f"评测 {version.label} ...", flush=True)
        version_results.append(await evaluator.evaluate_version(version, cases))

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "generated_at": generated_at,
        "cases": [asdict(case) for case in cases],
        "versions": [
            {
                "version": asdict(result.version),
                "aggregate": aggregate_version(result),
                "by_category": aggregate_by_category(result),
                "cases": [
                    {
                        **asdict(item),
                        "metrics": asdict(item.metrics),
                    }
                    for item in result.case_results
                ],
            }
            for result in version_results
        ],
    }

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = build_report(
        cases=cases,
        version_results=version_results,
        faq_count=len(faq_documents),
        chunk_count=len(chunk_documents),
        dense_doc_count=count_chroma_collection(settings.CHROMA_DOC_COLLECTION),
        dense_chunk_count=count_chroma_collection(settings.CHROMA_CHUNK_COLLECTION),
        generated_at=generated_at,
        suite=args.suite,
        json_output=args.json_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"完成。report={args.output} json={args.json_output}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
