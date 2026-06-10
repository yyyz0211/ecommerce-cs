import pytest

from app.rag.schemas import RAGDocument, RetrievalCandidate


def test_query_analyzer_extracts_category_and_keywords():
    from app.rag.planning.analyzer import analyze_query

    analysis = analyze_query("生鲜商品可以拒收吗？运费怎么算")

    assert analysis.category == "物流配送"
    assert "生鲜" in analysis.keywords
    assert "拒收" in analysis.keywords
    assert analysis.normalized_query == "生鲜商品可以拒收吗 运费怎么算"


def test_query_analyzer_marks_order_specific_queries():
    from app.rag.planning.analyzer import analyze_query

    analysis = analyze_query("我的订单 202605280001 到哪里了")

    assert analysis.needs_business_tool is True
    assert "订单" in analysis.keywords


def test_query_planner_builds_retrieval_plan():
    from app.rag.planning.planner import plan_query

    plan = plan_query("生鲜商品可以拒收吗？")

    assert plan.raw_query == "生鲜商品可以拒收吗？"
    assert plan.normalized_query == "生鲜商品可以拒收吗"
    assert plan.primary_query == "生鲜商品可以拒收吗"
    assert plan.category == "物流配送"
    assert plan.filters == {"category": "物流配送"}
    assert plan.retrieval_queries == ["生鲜商品可以拒收吗"]


def test_keyword_tokenizer_keeps_domain_terms():
    from app.rag.indexing.keyword_store import tokenize

    tokens = tokenize("七天无理由退货和货到付款发票")

    assert "七天无理由" in tokens
    assert "退货" in tokens
    assert "货到付款" in tokens
    assert "发票" in tokens


def test_merge_candidates_combines_sources_and_scores():
    from app.rag.retrieval.fusion import merge_candidates

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
    assert merged[0].fusion_score == 1.0
    assert merged[0].sources == ["dense_faq", "bm25"]


def test_merge_candidates_uses_rrf_rank_signal():
    from app.rag.retrieval.fusion import merge_candidates

    dense_top = RetrievalCandidate(
        id="a",
        faq_id="a",
        doc_type="faq",
        category="支付发票",
        question="退款规则",
        text="退款规则说明。",
        url="https://example.com/a",
        dense_score=0.7,
        sources=["dense_chunk"],
    )
    dense_second = dense_top.model_copy(update={"id": "c", "faq_id": "c", "question": "其他退款规则"})
    sparse_top = dense_top.model_copy(
        update={"id": "b", "faq_id": "b", "dense_score": None, "sparse_score": 1.0, "sources": ["bm25"]}
    )
    sparse_second_same_as_dense_top = dense_top.model_copy(
        update={"dense_score": None, "sparse_score": 0.8, "sources": ["bm25"]}
    )

    merged = merge_candidates([dense_top, dense_second], [sparse_top, sparse_second_same_as_dense_top])

    assert [candidate.id for candidate in merged] == ["a", "b", "c"]
    assert merged[0].sources == ["dense_chunk", "bm25"]
    assert merged[0].fusion_score == 1.0
    assert merged[0].fusion_score > merged[1].fusion_score
    assert merged[1].fusion_score > merged[2].fusion_score


def test_dense_retrieval_uses_category_as_soft_signal_only(monkeypatch):
    from app.rag.planning.planner import plan_query
    from app.rag.retrieval.dense import retrieve_dense

    seen_categories = []

    def fake_query_documents(query_embedding, *, top_k, category, collection_name):
        seen_categories.append(category)
        return []

    monkeypatch.setattr("app.rag.retrieval.dense.query_documents", fake_query_documents)

    plan = plan_query("退款一般几天到，为什么还没到账？")
    assert plan.category is not None

    retrieve_dense(plan, [0.1, 0.2], top_k=5)

    assert seen_categories == [None, None]


def test_sparse_retrieval_uses_category_as_soft_signal_only(monkeypatch):
    from app.rag.planning.planner import plan_query
    from app.rag.retrieval.sparse import retrieve_sparse

    seen_categories = []

    def fake_search_keyword_index(query, *, top_k, category):
        seen_categories.append(category)
        return []

    monkeypatch.setattr("app.rag.retrieval.sparse.search_keyword_index", fake_search_keyword_index)

    plan = plan_query("支付密码忘记了，现在付款付不了怎么找回？")
    assert plan.category is not None

    retrieve_sparse(plan, top_k=5)

    assert seen_categories == [None]


@pytest.mark.asyncio
async def test_pipeline_composes_retrieval_fusion_rerank_and_selection(monkeypatch):
    from app.rag.pipeline import run_rag_pipeline
    from app.rag.retrieval.hybrid import RetrievalChannels

    dense = RetrievalCandidate(
        id="dense",
        faq_id="dense",
        doc_type="faq",
        category="物流配送",
        question="生鲜拒收规则",
        text="生鲜暂不支持拒收。",
        url="https://example.com/dense",
        dense_score=0.8,
        sources=["dense_faq"],
    )
    sparse = dense.model_copy(update={"dense_score": None, "sparse_score": 1.0, "sources": ["bm25"]})

    async def fake_embed_query(query: str):
        return [0.1, 0.2]

    def fake_retrieve_candidates(plan, query_embedding, *, dense_top_k, sparse_top_k):
        assert plan.primary_query == "生鲜商品可以拒收吗"
        assert query_embedding == [0.1, 0.2]
        assert dense_top_k == 5
        assert sparse_top_k == 5
        return RetrievalChannels(dense_faq=[dense], dense_chunk=[], sparse=[sparse])

    monkeypatch.setattr("app.rag.pipeline.embed_query", fake_embed_query)
    monkeypatch.setattr("app.rag.pipeline.retrieve_candidates", fake_retrieve_candidates)

    trace = await run_rag_pipeline("生鲜商品可以拒收吗？", top_k=1, dense_top_k=5, sparse_top_k=5)

    assert trace.analysis.primary_query == "生鲜商品可以拒收吗"
    assert trace.dense_faq == [dense]
    assert trace.sparse == [sparse]
    assert len(trace.merged) == 1
    assert trace.reranked[0].id == "dense"
    assert trace.selection.contexts[0].id == "dense"


def test_reranker_prefers_category_and_keyword_overlap():
    from app.rag.planning.analyzer import analyze_query
    from app.rag.reranking.rule import rerank_candidates

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


def test_reranker_records_matched_document_keywords():
    from app.rag.schemas import QueryAnalysis
    from app.rag.reranking.rule import rerank_candidates

    analysis = QueryAnalysis(
        raw_query="怎么改支付密码",
        normalized_query="怎么改支付密码",
        category="账户管理",
        keywords=["修改支付密码", "支付密码"],
    )
    candidate = RetrievalCandidate(
        id="payment-password",
        faq_id="payment-password",
        doc_type="faq",
        category="账户管理",
        question="如何修改支付密码？",
        text="在账户安全中修改。",
        url="https://example.com/payment-password",
        keywords=["修改支付密码", "支付密码", "账户安全"],
        fusion_score=1.0,
        sources=["dense_faq", "bm25"],
    )

    ranked = rerank_candidates([candidate], analysis)

    assert ranked[0].matched_keywords == ["修改支付密码", "支付密码"]


def test_context_selector_keeps_diverse_faqs_under_budget():
    from app.rag.evidence.selector import select_contexts

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
    from app.rag.indexing.loader import load_faq_documents

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
