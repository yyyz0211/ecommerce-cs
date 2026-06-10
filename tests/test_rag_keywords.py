import json


def test_build_keyword_vocabulary_keeps_only_terms_seen_in_rows():
    from app.rag.indexing.keyword_taxonomy import build_keyword_vocabulary

    rows = [
        {
            "id": "faq-1",
            "category": "账户管理",
            "question": "如何修改支付密码？",
            "text": "您可以在账户安全中修改支付密码。",
            "kb_candidate": True,
        }
    ]

    vocabulary = build_keyword_vocabulary(rows, min_doc_count=1)
    names = {item["canonical"] for item in vocabulary["keywords"]}

    assert "修改支付密码" in names
    assert "支付密码" in names
    assert "退款时效" not in names


def test_extract_document_keywords_selects_vocab_terms_with_evidence():
    from app.rag.indexing.keyword_taxonomy import build_keyword_vocabulary, extract_document_keywords

    rows = [
        {
            "id": "faq-1",
            "category": "账户管理",
            "question": "如何修改支付密码？",
            "text": "您可以在账户安全中修改支付密码。",
            "kb_candidate": True,
        }
    ]
    vocabulary = build_keyword_vocabulary(rows, min_doc_count=1)

    result = extract_document_keywords(
        {
            "category": "账户管理",
            "question": "如何修改支付密码？",
            "text": "您可以在账户安全中修改支付密码。",
        },
        vocabulary,
    )

    assert result["keywords"][:3] == ["修改支付密码", "支付密码", "账户安全"]
    assert result["keyword_evidence"]["修改支付密码"]
    assert result["keyword_confidence"]["修改支付密码"] > 0


def test_annotate_chunk_keywords_inherits_faq_keywords_and_adds_local_terms():
    from app.rag.indexing.keyword_taxonomy import annotate_chunk_keywords, build_keyword_vocabulary

    rows = [
        {
            "id": "faq-1",
            "category": "售后政策",
            "question": "退款的时效是多久？",
            "text": "退款完成后会原路退回，到账时间以支付方式为准。",
            "kb_candidate": True,
        },
        {
            "id": "faq-2",
            "category": "售后政策",
            "question": "京东自营上门取件收费标准及收费方式",
            "text": "上门取件时可能收取取件收费，退货运费可从退款中扣减。",
            "kb_candidate": True,
        },
    ]
    vocabulary = build_keyword_vocabulary(rows, min_doc_count=1)

    chunk = {
        "faq_id": "faq-2",
        "category": "售后政策",
        "question": "京东自营上门取件收费标准及收费方式",
        "text": "退货会生成上门取件单，取件收费可从退款中扣减。",
    }
    annotated = annotate_chunk_keywords(chunk, vocabulary, faq_keywords=["上门取件", "取件收费"])

    assert "上门取件" in annotated["keywords"]
    assert "取件收费" in annotated["keywords"]
    assert "退款" in annotated["keywords"]


def test_keyword_annotation_output_is_json_serializable():
    from app.rag.indexing.keyword_taxonomy import build_keyword_vocabulary, extract_document_keywords

    rows = [
        {
            "id": "faq-1",
            "category": "支付发票",
            "question": "支付方式有哪些？如何支付？",
            "text": "京东支持在线支付、白条、货到付款等支付方式。",
            "kb_candidate": True,
        }
    ]
    vocabulary = build_keyword_vocabulary(rows, min_doc_count=1)
    result = extract_document_keywords(rows[0], vocabulary)

    json.dumps(result, ensure_ascii=False)


def test_extract_document_keywords_drops_weak_cross_category_text_only_terms():
    from app.rag.indexing.keyword_taxonomy import build_keyword_vocabulary, extract_document_keywords

    rows = [
        {
            "id": "faq-1",
            "category": "售后政策",
            "question": "京东自营上门取件收费标准及收费方式",
            "text": "退货会生成上门取件单。新订单可以送货上门或自提。",
            "kb_candidate": True,
        },
        {
            "id": "faq-2",
            "category": "物流配送",
            "question": "如何使用自提？",
            "text": "用户可以选择自提点自提。",
            "kb_candidate": True,
        },
    ]
    vocabulary = build_keyword_vocabulary(rows, min_doc_count=1)

    result = extract_document_keywords(rows[0], vocabulary)

    assert "上门取件" in result["keywords"]
    assert "自提" not in result["keywords"]


def test_extract_document_keywords_prefers_question_intent_over_repeated_body_terms():
    from app.rag.indexing.keyword_taxonomy import build_keyword_vocabulary, extract_document_keywords

    row = {
        "id": "faq-1",
        "category": "支付发票",
        "question": "退款的时效是多久？",
        "text": "白条支付的退款会按支付方式退回。白条订单退款后额度恢复，白条账单同步更新。",
        "kb_candidate": True,
    }
    vocabulary = build_keyword_vocabulary([row], min_doc_count=1)

    result = extract_document_keywords(row, vocabulary)

    assert result["keywords"][0] == "退款时效"


def test_loaders_preserve_keywords_from_enriched_jsonl(tmp_path):
    from app.rag.indexing.loader import load_documents, load_faq_documents

    clean_path = tmp_path / "clean.jsonl"
    clean_path.write_text(
        json.dumps(
            {
                "id": "faq-1",
                "source": "京东帮助中心",
                "category": "账户管理",
                "question": "如何修改支付密码？",
                "text": "问题：如何修改支付密码？\n答案：在账户安全中修改。",
                "url": "https://example.com/faq-1",
                "kb_candidate": True,
                "keywords": ["修改支付密码", "支付密码", "账户安全"],
                "keyword_version": "jd_faq_keywords_v1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(
        json.dumps(
            {
                "id": "faq-1-000",
                "faq_id": "faq-1",
                "chunk_index": 0,
                "chunk_count": 1,
                "source": "京东帮助中心",
                "category": "账户管理",
                "question": "如何修改支付密码？",
                "text": "在账户安全中修改支付密码。",
                "url": "https://example.com/faq-1",
                "keywords": ["修改支付密码", "支付密码"],
                "keyword_version": "jd_faq_keywords_v1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    faq_documents = load_faq_documents(clean_path)
    chunk_documents = load_documents(chunks_path)

    assert faq_documents[0].keywords == ["修改支付密码", "支付密码", "账户安全"]
    assert faq_documents[0].keyword_version == "jd_faq_keywords_v1"
    assert chunk_documents[0].keywords == ["修改支付密码", "支付密码"]


def test_bm25_document_tokens_weight_keywords():
    from app.rag.indexing.keyword_store import tokenize_document
    from app.rag.schemas import RAGDocument

    document = RAGDocument(
        id="faq:1",
        faq_id="1",
        doc_type="faq",
        category="账户管理",
        question="如何修改支付密码？",
        text="在账户安全中处理。",
        url="https://example.com/1",
        keywords=["修改支付密码", "支付密码", "账户安全"],
    )

    tokens = tokenize_document(document)

    assert tokens.count("修改支付密码") >= 4
    assert tokens.count("支付密码") >= 4


def test_bm25_search_returns_document_keywords():
    from app.rag.indexing.keyword_store import KeywordSearchIndex, tokenize_document
    from app.rag.schemas import RAGDocument

    document = RAGDocument(
        id="faq:1",
        faq_id="1",
        doc_type="faq",
        category="账户管理",
        question="如何修改支付密码？",
        text="在账户安全中修改支付密码。",
        url="https://example.com/1",
        keywords=["修改支付密码", "支付密码", "账户安全"],
        keyword_version="jd_faq_keywords_v1",
    )
    other = RAGDocument(
        id="faq:2",
        faq_id="2",
        doc_type="faq",
        category="物流配送",
        question="如何查询物流？",
        text="可以在订单详情查看物流。",
        url="https://example.com/2",
    )
    another = other.model_copy(
        update={
            "id": "faq:3",
            "faq_id": "3",
            "question": "如何开发票？",
            "text": "可以在订单详情申请发票。",
        }
    )
    documents = [document, other, another]
    index = KeywordSearchIndex(documents, [tokenize_document(item) for item in documents])

    matches = index.search("修改支付密码", top_k=1)

    assert matches[0].keywords == ["修改支付密码", "支付密码", "账户安全"]
    assert matches[0].keyword_version == "jd_faq_keywords_v1"


def test_tokenize_query_expands_aliases_to_canonical_keywords():
    from app.rag.indexing.keyword_store import tokenize_query

    payment_tokens = tokenize_query("我想改一下支付密码，在哪里改？")
    refund_tokens = tokenize_query("退款一般几天到，为什么还没到账？")

    assert "修改支付密码" in payment_tokens
    assert "支付密码" in payment_tokens
    assert "退款时效" in refund_tokens
    assert "为什么" not in refund_tokens
    assert "没到" not in refund_tokens
    assert "账" not in refund_tokens


def test_tokenize_keeps_protected_terms_in_vocabulary_order(monkeypatch):
    from app.rag.indexing import keyword_store

    monkeypatch.setattr(keyword_store, "get_protected_terms", lambda: ("退款", "支付密码", "修改支付密码"))

    tokens = keyword_store.tokenize("退款和修改支付密码")

    assert tokens[:3] == ["退款", "支付密码", "修改支付密码"]


def test_keyword_vocabulary_loads_configured_vocab(tmp_path):
    from app.rag.indexing.keyword_vocabulary import load_keyword_vocabulary

    vocab_path = tmp_path / "keyword_vocab.json"
    vocab_path.write_text(
        json.dumps(
            {
                "version": "test_vocab",
                "keywords": [
                    {
                        "id": "test.delivery_address",
                        "canonical": "修改配送地址",
                        "category": "物流配送",
                        "aliases": ["改收货地"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    vocabulary = load_keyword_vocabulary(str(vocab_path))

    assert vocabulary["version"] == "test_vocab"
    assert vocabulary["keywords"][0]["canonical"] == "修改配送地址"


def test_keyword_vocabulary_derives_protected_terms_from_configured_vocab(tmp_path):
    from app.rag.indexing.keyword_vocabulary import derive_protected_terms, load_keyword_vocabulary

    vocab_path = tmp_path / "keyword_vocab.json"
    vocab_path.write_text(
        json.dumps(
            {
                "version": "test_vocab",
                "keywords": [
                    {
                        "id": "test.delivery_address",
                        "canonical": "修改配送地址",
                        "category": "物流配送",
                        "aliases": ["改收货地"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    protected_terms = derive_protected_terms(load_keyword_vocabulary(str(vocab_path)))

    assert "修改配送地址" in protected_terms
    assert "改收货地" in protected_terms


def test_bm25_protected_terms_are_loaded_from_configured_keyword_vocab(tmp_path, monkeypatch):
    from app.config import settings
    from app.rag.indexing import keyword_store
    from app.rag.indexing import keyword_vocabulary

    vocab_path = tmp_path / "keyword_vocab.json"
    vocab_path.write_text(
        json.dumps(
            {
                "version": "test_vocab",
                "keywords": [
                    {
                        "id": "test.delivery_address",
                        "canonical": "修改配送地址",
                        "category": "物流配送",
                        "aliases": ["改收货地"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "KEYWORD_VOCAB_PATH", str(vocab_path), raising=False)
    keyword_vocabulary.load_keyword_vocabulary.cache_clear()
    keyword_store.get_protected_terms.cache_clear()

    protected_terms = keyword_store.get_protected_terms()

    assert "修改配送地址" in protected_terms
    assert "改收货地" in protected_terms


def test_tokenize_query_maps_aliases_from_configured_keyword_vocab(tmp_path, monkeypatch):
    from app.config import settings
    from app.rag.indexing import keyword_store
    from app.rag.indexing import keyword_vocabulary

    vocab_path = tmp_path / "keyword_vocab.json"
    vocab_path.write_text(
        json.dumps(
            {
                "version": "test_vocab",
                "keywords": [
                    {
                        "id": "test.delivery_address",
                        "canonical": "修改配送地址",
                        "category": "物流配送",
                        "aliases": ["改收货地"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "KEYWORD_VOCAB_PATH", str(vocab_path), raising=False)
    keyword_vocabulary.load_keyword_vocabulary.cache_clear()
    keyword_store.get_protected_terms.cache_clear()

    tokens = keyword_store.tokenize_query("我要改收货地")

    assert "修改配送地址" in tokens


def test_chroma_embedding_text_includes_keywords():
    from app.rag.schemas import RAGDocument
    from scripts.build_jd_faq_chroma import embedding_text_for_document

    document = RAGDocument(
        id="faq:1",
        faq_id="1",
        doc_type="faq",
        category="账户管理",
        question="如何修改支付密码？",
        text="在账户安全中修改。",
        url="https://example.com/1",
        keywords=["修改支付密码", "支付密码", "账户安全"],
    )

    text = embedding_text_for_document(document)

    assert "关键词：修改支付密码，支付密码，账户安全" in text
    assert "问题：如何修改支付密码？" in text


def test_rag_build_scripts_default_to_keyword_enriched_inputs():
    import scripts.build_jd_faq_chroma as chroma_script
    import scripts.build_jd_faq_keyword_index as bm25_script

    assert bm25_script.DEFAULT_CLEAN_INPUT.name == "jd_faq_clean_keywords.jsonl"
    assert bm25_script.DEFAULT_CHUNKS_INPUT.name == "jd_faq_chunks_keywords.jsonl"
    assert chroma_script.DEFAULT_CLEAN_INPUT.name == "jd_faq_clean_keywords.jsonl"
    assert chroma_script.DEFAULT_CHUNKS_INPUT.name == "jd_faq_chunks_keywords.jsonl"
