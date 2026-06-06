from app.rag.schemas import RAGDocument, RetrievalCandidate


def test_query_analyzer_extracts_category_and_keywords():
    from app.rag.query_analyzer import analyze_query

    analysis = analyze_query("生鲜商品可以拒收吗？运费怎么算")

    assert analysis.category == "物流配送"
    assert "生鲜" in analysis.keywords
    assert "拒收" in analysis.keywords
    assert analysis.normalized_query == "生鲜商品可以拒收吗 运费怎么算"


def test_query_analyzer_marks_order_specific_queries():
    from app.rag.query_analyzer import analyze_query

    analysis = analyze_query("我的订单 202605280001 到哪里了")

    assert analysis.needs_business_tool is True
    assert "订单" in analysis.keywords


def test_keyword_tokenizer_keeps_domain_terms():
    from app.rag.keyword_store import tokenize

    tokens = tokenize("七天无理由退货和货到付款发票")

    assert "七天无理由" in tokens
    assert "退货" in tokens
    assert "货到付款" in tokens
    assert "发票" in tokens


def test_merge_candidates_combines_sources_and_scores():
    from app.rag.hybrid_retriever import merge_candidates

    dense = RetrievalCandidate(
        id="faq-1",
        faq_id="faq-1",
        doc_type="faq",
        category="售后政策",
        question="七天无理由退货规则",
        text="支持七天无理由退货。",
        url="https://example.com/a",
        dense_score=0.82,
        sources=["dense_faq"],
    )
    sparse = dense.model_copy(update={"dense_score": None, "sparse_score": 0.6, "sources": ["bm25"]})

    merged = merge_candidates([dense], [sparse])

    assert len(merged) == 1
    assert merged[0].dense_score == 0.82
    assert merged[0].sparse_score == 0.6
    assert merged[0].sources == ["dense_faq", "bm25"]


def test_reranker_prefers_category_and_keyword_overlap():
    from app.rag.query_analyzer import analyze_query
    from app.rag.reranker import rerank_candidates

    analysis = analyze_query("生鲜商品可以拒收吗")
    good = RetrievalCandidate(
        id="good",
        faq_id="good",
        doc_type="chunk",
        category="物流配送",
        question="生鲜商品配送拒收规则",
        text="生鲜商品签收和拒收规则。",
        url="https://example.com/good",
        dense_score=0.5,
        sparse_score=0.4,
        sources=["dense_chunk", "bm25"],
    )
    weak = RetrievalCandidate(
        id="weak",
        faq_id="weak",
        doc_type="chunk",
        category="支付发票",
        question="发票怎么开",
        text="发票开具规则。",
        url="https://example.com/weak",
        dense_score=0.6,
        sparse_score=0.0,
        sources=["dense_chunk"],
    )

    ranked = rerank_candidates([weak, good], analysis)

    assert ranked[0].id == "good"
    assert ranked[0].final_score is not None
    assert any("category_match" in reason for reason in ranked[0].rerank_reasons)
    assert any("keyword_overlap" in reason for reason in ranked[0].rerank_reasons)


def test_context_selector_keeps_diverse_faqs_under_budget():
    from app.rag.context_selector import select_contexts

    candidates = [
        RetrievalCandidate(
            id="a-0",
            faq_id="a",
            doc_type="chunk",
            category="物流配送",
            question="拒收规则 A",
            text="A" * 60,
            url="https://example.com/a",
            final_score=0.9,
        ),
        RetrievalCandidate(
            id="a-1",
            faq_id="a",
            doc_type="chunk",
            category="物流配送",
            question="拒收规则 A",
            text="A" * 60,
            url="https://example.com/a",
            final_score=0.8,
        ),
        RetrievalCandidate(
            id="b-0",
            faq_id="b",
            doc_type="chunk",
            category="物流配送",
            question="拒收规则 B",
            text="B" * 60,
            url="https://example.com/b",
            final_score=0.7,
        ),
    ]

    selection = select_contexts(candidates, top_k=2, max_chars=160)

    assert [item.faq_id for item in selection.contexts] == ["a", "b"]
    assert selection.coverage == "partial"


def test_loader_builds_faq_level_documents(tmp_path):
    from app.rag.loader import load_faq_documents

    path = tmp_path / "clean.jsonl"
    path.write_text(
        '{"id":"x","source":"京东帮助中心","category":"售后政策","question":"退货规则","text":"问题：退货规则\\n答案：支持退货","url":"https://example.com/x","kb_candidate":true}\n'
        '{"id":"y","source":"京东帮助中心","category":"售后政策","question":"公告","text":"公告内容","url":"https://example.com/y","kb_candidate":false}\n',
        encoding="utf-8",
    )

    docs = load_faq_documents(path)

    assert len(docs) == 1
    assert docs[0].id == "faq:x"
    assert docs[0].doc_type == "faq"
