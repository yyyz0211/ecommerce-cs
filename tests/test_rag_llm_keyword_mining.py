import json


def test_parse_llm_json_accepts_markdown_fence():
    from app.rag.indexing.llm_keyword_mining import parse_llm_json

    payload = parse_llm_json(
        """```json
        {"expressions": [{"text": "改支付密码", "category": "账户管理"}]}
        ```"""
    )

    assert payload["expressions"][0]["text"] == "改支付密码"


def test_normalize_mined_expressions_counts_duplicates_and_filters_generic_terms():
    from app.rag.indexing.llm_keyword_mining import normalize_mined_expressions

    payload = {
        "expressions": [
            {"text": "改支付密码", "category": "账户管理", "faq_ids": ["a"]},
            {"text": "改支付密码", "category": "账户管理", "faq_ids": ["b"]},
            {"text": "商品", "category": "售后政策", "faq_ids": ["c"]},
            {"text": "未知词", "category": "未知分类", "faq_ids": ["d"]},
        ]
    }

    normalized = normalize_mined_expressions(payload)

    assert normalized["expression_count"] == 1
    assert normalized["expressions"][0]["text"] == "改支付密码"
    assert normalized["expressions"][0]["count"] == 2
    assert normalized["expressions"][0]["faq_ids"] == ["a", "b"]
    assert normalized["rejected_count"] == 2


def test_normalize_keyword_clusters_merges_aliases_and_marks_existing_terms():
    from app.rag.indexing.llm_keyword_mining import normalize_keyword_clusters

    existing = {
        "keywords": [
            {
                "id": "account.modify_payment_password",
                "canonical": "修改支付密码",
                "category": "账户管理",
                "aliases": ["改支付密码"],
            }
        ]
    }
    raw = {
        "clusters": [
            {
                "canonical": "更改支付密码",
                "category": "账户管理",
                "aliases": ["改支付密码", "付款密码怎么改"],
                "source_expressions": ["改支付密码", "更改支付密码"],
            }
        ]
    }

    vocab = normalize_keyword_clusters(raw, existing_vocabulary=existing)

    assert vocab["keyword_count"] == 1
    item = vocab["keywords"][0]
    assert item["canonical"] == "修改支付密码"
    assert item["existing_keyword"] is True
    assert "付款密码怎么改" in item["aliases"]
    assert item["source"] == "llm_cluster"


def test_normalized_keyword_clusters_reject_invalid_clusters():
    from app.rag.indexing.llm_keyword_mining import normalize_keyword_clusters

    raw = {
        "clusters": [
            {"canonical": "商品", "category": "售后政策", "aliases": []},
            {"canonical": "发票抬头", "category": "支付发票", "aliases": ["公司抬头"]},
            {"canonical": "自定义词", "category": "未知分类", "aliases": []},
        ]
    }

    vocab = normalize_keyword_clusters(raw)

    assert [item["canonical"] for item in vocab["keywords"]] == ["发票抬头"]
    assert vocab["rejected_count"] == 2


def test_llm_keyword_vocab_is_json_serializable():
    from app.rag.indexing.llm_keyword_mining import normalize_keyword_clusters

    vocab = normalize_keyword_clusters(
        {"clusters": [{"canonical": "退款时效", "category": "售后政策", "aliases": ["退款多久"]}]}
    )

    json.dumps(vocab, ensure_ascii=False)


def test_build_expression_mining_prompt_asks_for_raw_expressions():
    from scripts.mine_jd_faq_keyword_expressions_llm import build_expression_mining_prompt

    prompt = build_expression_mining_prompt(
        "账户管理",
        [{"id": "faq-1", "question": "如何修改支付密码？", "answer": "在账户安全中修改。"}],
        max_expressions=20,
    )

    assert "统计原始表达" in prompt
    assert "expressions" in prompt
    assert "如何修改支付密码？" in prompt


def test_build_keyword_clustering_prompt_asks_for_canonical_clusters():
    from scripts.cluster_jd_faq_keyword_expressions_llm import build_keyword_clustering_prompt

    prompt = build_keyword_clustering_prompt(
        "账户管理",
        [{"text": "改支付密码", "count": 3}, {"text": "更改支付密码", "count": 2}],
        max_keywords=10,
    )

    assert "合并意思相近" in prompt
    assert "clusters" in prompt
    assert "canonical" in prompt


def test_cluster_script_creates_output_parent_directories(tmp_path):
    from scripts.cluster_jd_faq_keyword_expressions_llm import write_keyword_outputs

    output = tmp_path / "nested" / "vocab" / "keywords.json"
    review_output = tmp_path / "nested" / "review" / "keywords.md"
    vocab = {
        "keyword_count": 1,
        "existing_keyword_count": 0,
        "new_keyword_count": 1,
        "rejected_count": 0,
        "keywords": [
            {
                "canonical": "退款时效",
                "category": "售后政策",
                "aliases": ["退款多久"],
                "source_expressions": ["退款多久"],
            }
        ],
    }

    write_keyword_outputs(vocab, output=output, review_output=review_output)

    assert output.exists()
    assert review_output.exists()
