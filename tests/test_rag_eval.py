import argparse
from unittest.mock import AsyncMock

import pytest

from app.rag.schemas import ContextSelection, RAGDocument, RetrievalCandidate
from scripts.rag_eval import (
    EVAL_VERSIONS,
    EvalCase,
    RagEvaluator,
    apply_suite_defaults,
    compute_case_metrics,
    keyword_overlap_score,
    load_eval_cases,
    merge_candidates_weighted_rrf,
    rank_candidates_for_v4,
    rank_dense_with_bm25_boost,
)


def candidate(faq_id: str, *, dense_score=None, sparse_score=None, category="物流配送"):
    return RetrievalCandidate(
        id=f"faq:{faq_id}",
        faq_id=faq_id,
        doc_type="faq",
        category=category,
        question=f"问题 {faq_id}",
        text=f"答案 {faq_id}",
        url=f"https://example.com/{faq_id}",
        dense_score=dense_score,
        sparse_score=sparse_score,
        sources=[],
    )


def test_eval_versions_are_ordered_from_baseline_to_current():
    assert [version.key for version in EVAL_VERSIONS] == [
        "rag_v0_keyword",
        "rag_v1_bm25_faq",
        "rag_v2_dense_chunk",
        "rag_v3_dense_faq_chunk",
        "rag_v4_dense_bm25_hybrid",
        "rag_v5_hybrid_fusion",
        "rag_v5a_weighted_rrf",
        "rag_v5b_bm25_top5_rrf",
        "rag_v5c_dense_bm25_boost",
        "rag_v5d_dense_bm25_light_boost",
        "rag_v6_hybrid_fusion_rule_rerank",
        "rag_v7_current",
    ]


def test_compute_case_metrics_records_recall_mrr_and_category():
    metrics = compute_case_metrics(
        expected_faq_ids={"target"},
        expected_category="物流配送",
        candidates=[
            candidate("other", category="物流配送"),
            candidate("target", category="售后政策"),
        ],
    )

    assert metrics.hit_at_1 == 0
    assert metrics.hit_at_3 == 1
    assert metrics.hit_at_5 == 1
    assert metrics.mrr == 0.5
    assert metrics.category_hit_at_1 == 1
    assert metrics.first_hit_rank == 2


def test_keyword_overlap_score_rewards_query_terms_in_question_and_text():
    good = candidate("good")
    good = good.model_copy(update={"question": "生鲜商品可以拒收吗", "text": "生鲜暂不支持拒收"})
    weak = candidate("weak")
    weak = weak.model_copy(update={"question": "如何开发票", "text": "发票开具规则"})

    assert keyword_overlap_score("生鲜商品拒收", good) > keyword_overlap_score("生鲜商品拒收", weak)


def test_v4_ranking_uses_best_available_channel_score():
    sparse = candidate("sparse", sparse_score=1.0)
    dense = candidate("dense", dense_score=0.7)
    weak = candidate("weak", dense_score=0.1, sparse_score=0.2)

    ranked = rank_candidates_for_v4([weak, dense, sparse])

    assert [item.faq_id for item in ranked] == ["sparse", "dense", "weak"]


def test_weighted_rrf_can_downweight_sparse_noise():
    dense = candidate("dense", dense_score=0.7)
    sparse_noise = candidate("sparse_noise", sparse_score=1.0)

    ranked = merge_candidates_weighted_rrf(
        ([dense], 1.0),
        ([sparse_noise], 0.2),
    )

    assert [item.faq_id for item in ranked] == ["dense", "sparse_noise"]


def test_dense_with_bm25_boost_prefers_dense_order_and_adds_same_faq_signal():
    target = candidate("target", dense_score=0.8)
    other = candidate("other", dense_score=0.82)
    sparse_same_faq = candidate("target", sparse_score=1.0)
    sparse_only = candidate("sparse_only", sparse_score=1.0)

    ranked = rank_dense_with_bm25_boost([target, other], [sparse_same_faq, sparse_only])

    assert [item.faq_id for item in ranked[:2]] == ["target", "other"]
    assert any(reason.startswith("bm25_same_faq_boost") for reason in ranked[0].rerank_reasons)
    assert ranked[-1].faq_id == "sparse_only"


@pytest.mark.asyncio
async def test_eval_v7_uses_dense_primary_merge_like_production_pipeline(monkeypatch):
    from app.rag.retrieval.hybrid import RetrievalChannels

    dense = candidate("dense", dense_score=0.8)
    sparse = candidate("dense", sparse_score=1.0)
    document = RAGDocument(
        id="dense",
        faq_id="dense",
        doc_type="faq",
        category="物流配送",
        question="生鲜拒收规则",
        text="生鲜暂不支持拒收。",
        url="https://example.com/dense",
    )
    evaluator = RagEvaluator(
        faq_documents=[document],
        chunk_documents=[document],
        top_k=1,
        dense_top_k=5,
        sparse_top_k=5,
        max_context_chars=1000,
    )
    evaluator.embed_for_eval = AsyncMock(return_value=[0.1, 0.2])
    seen = {}

    def fake_retrieve_candidates(plan, query_embedding, *, dense_top_k, sparse_top_k):
        return RetrievalChannels(dense_faq=[dense], dense_chunk=[], sparse=[sparse])

    def fake_merge_candidates_dense_primary(dense_candidates, sparse_candidates, *, same_faq_boost):
        seen["dense_candidates"] = list(dense_candidates)
        seen["sparse_candidates"] = list(sparse_candidates)
        seen["same_faq_boost"] = same_faq_boost
        return [dense.model_copy(update={"fusion_score": 0.82, "final_score": 0.82})]

    def fake_rerank_candidates(candidates, plan):
        return candidates

    def fake_select_evidence(candidates, *, query, top_k, max_chars):
        return ContextSelection(query=query, contexts=candidates[:top_k], coverage="ok", total_chars=0)

    monkeypatch.setattr("scripts.rag_eval.retrieve_candidates", fake_retrieve_candidates)
    monkeypatch.setattr("scripts.rag_eval.merge_candidates_dense_primary", fake_merge_candidates_dense_primary)
    monkeypatch.setattr("scripts.rag_eval.rerank_candidates", fake_rerank_candidates)
    monkeypatch.setattr("scripts.rag_eval.select_evidence", fake_select_evidence)

    case = EvalCase(
        id="case",
        query="生鲜商品可以拒收吗",
        category="物流配送",
        expected_faq_ids=["dense"],
        expected_titles=["生鲜拒收规则"],
        difficulty="hard",
        tags=[],
    )

    result = await evaluator.run_version("rag_v7_current", case)

    assert seen["dense_candidates"] == [dense]
    assert seen["sparse_candidates"] == [sparse]
    assert seen["same_faq_boost"] == 0.02
    assert result[0].final_score == 0.82


def test_production_like_suite_uses_independent_default_paths():
    args = argparse.Namespace(
        suite="production_like",
        cases=None,
        output=None,
        json_output=None,
    )

    apply_suite_defaults(args)

    assert args.cases.name == "production_like_cases.jsonl"
    assert args.output.name == "production_like_eval_report.md"
    assert args.json_output.name == "production_like_eval_results.json"


def test_explicit_paths_override_suite_defaults(tmp_path):
    args = argparse.Namespace(
        suite="production_like",
        cases=tmp_path / "custom_cases.jsonl",
        output=tmp_path / "custom_report.md",
        json_output=tmp_path / "custom_results.json",
    )

    apply_suite_defaults(args)

    assert args.cases == tmp_path / "custom_cases.jsonl"
    assert args.output == tmp_path / "custom_report.md"
    assert args.json_output == tmp_path / "custom_results.json"


def test_load_eval_cases_accepts_production_like_metadata(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"id":"p1","query":"钱啥时候退回来","category":"支付发票","expected_faq_ids":["x"],'
        '"expected_titles":["退款的时效是多久？"],"difficulty":"hard","tags":["口语化"],'
        '"source":"synthetic_production_like","should_use_rag":true,"should_use_business_tool":false}\n',
        encoding="utf-8",
    )

    cases = load_eval_cases(path)

    assert cases[0].source == "synthetic_production_like"
    assert cases[0].should_use_rag is True
    assert cases[0].should_use_business_tool is False
