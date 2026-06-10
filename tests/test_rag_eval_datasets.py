import json
from pathlib import Path

from scripts.rag_eval import load_eval_cases


ROOT_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT_DIR / "data" / "rag_eval"


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def test_supplemental_eval_datasets_are_valid_and_separated_by_purpose():
    datasets = {
        "retrieval_hard_cases.jsonl": "rag_positive_hard",
        "routing_cases.jsonl": "business_tool_routing",
        "no_answer_cases.jsonl": "no_answer_negative",
    }
    all_ids = []

    for filename, expected_source in datasets.items():
        path = DATASET_DIR / filename
        payloads = read_jsonl(path)
        cases = load_eval_cases(path)

        assert len(payloads) == len(cases)
        assert payloads
        assert {item["source"] for item in payloads} == {expected_source}
        all_ids.extend(item["id"] for item in payloads)

    assert len(all_ids) == len(set(all_ids))


def test_retrieval_hard_cases_are_positive_rag_cases_with_expected_answers():
    cases = load_eval_cases(DATASET_DIR / "retrieval_hard_cases.jsonl")

    assert len(cases) >= 20
    assert all(case.should_use_rag for case in cases)
    assert all(not case.should_use_business_tool for case in cases)
    assert all(case.expected_faq_ids for case in cases)
    assert all(case.expected_titles for case in cases)


def test_production_like_cases_include_supplemental_hard_retrieval_cases():
    cases = load_eval_cases(DATASET_DIR / "production_like_cases.jsonl")
    ids = {case.id for case in cases}

    assert len(cases) >= 124
    assert "hard_retrieval_001" in ids
    assert "hard_retrieval_024" in ids


def test_retrieval_hard_expected_faq_ids_exist_in_knowledge_base():
    faq_rows = read_jsonl(ROOT_DIR / "data" / "jd_faq_clean_keywords.jsonl")
    known_faq_ids = {row.get("faq_id") or row.get("id") for row in faq_rows}

    cases = load_eval_cases(DATASET_DIR / "retrieval_hard_cases.jsonl")
    missing = {
        faq_id
        for case in cases
        for faq_id in case.expected_faq_ids
        if faq_id not in known_faq_ids
    }

    assert missing == set()


def test_routing_and_no_answer_cases_are_not_plain_retrieval_positive_cases():
    routing_cases = load_eval_cases(DATASET_DIR / "routing_cases.jsonl")
    no_answer_cases = load_eval_cases(DATASET_DIR / "no_answer_cases.jsonl")

    assert len(routing_cases) >= 12
    assert all(not case.should_use_rag for case in routing_cases)
    assert all(case.should_use_business_tool for case in routing_cases)
    assert all(not case.expected_faq_ids for case in routing_cases)

    assert len(no_answer_cases) >= 12
    assert all(not case.should_use_rag for case in no_answer_cases)
    assert all(not case.should_use_business_tool for case in no_answer_cases)
    assert all(not case.expected_faq_ids for case in no_answer_cases)
