import argparse

from app.rag.schemas import RetrievalCandidate
from scripts.rag_eval import (
    EVAL_VERSIONS,
    apply_suite_defaults,
    compute_case_metrics,
    keyword_overlap_score,
    load_eval_cases,
    rank_candidates_for_v4,
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
