"""Chinese BM25 keyword index for JD FAQ retrieval."""

from __future__ import annotations

import math
import pickle
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

from app.config import settings
from app.rag.query_analyzer import DOMAIN_TERMS
from app.rag.schemas import RAGDocument, RetrievalCandidate


STOPWORDS = {
    "的",
    "了",
    "和",
    "与",
    "及",
    "或",
    "吗",
    "呢",
    "怎么",
    "如何",
    "可以",
    "是否",
    "什么",
    "京东",
    "商品",
}


def _load_jieba():
    try:
        import jieba
    except ModuleNotFoundError:
        return None
    for term in DOMAIN_TERMS:
        # 领域短语必须强制加入词典，否则“七天无理由/货到付款”等会被切碎。
        jieba.add_word(term, freq=200000)
    return jieba


def _fallback_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for term in DOMAIN_TERMS:
        if term in text:
            tokens.append(term)
    tokens.extend(re.findall(r"[A-Za-z0-9_]{2,}", text))
    tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return tokens


def tokenize(text: str) -> list[str]:
    """Tokenize Chinese text for BM25 with domain-term protection."""
    normalized = re.sub(r"\s+", " ", text.strip())
    jieba = _load_jieba()
    raw_tokens = jieba.lcut(normalized) if jieba else _fallback_tokens(normalized)

    tokens: list[str] = []
    seen_domain_terms = {term for term in DOMAIN_TERMS if term in normalized}
    for term in seen_domain_terms:
        tokens.append(term)

    for token in raw_tokens:
        token = token.strip()
        if not token or token in STOPWORDS:
            continue
        if len(token) == 1 and not token.isalnum():
            continue
        tokens.append(token)
    return tokens


class SimpleBM25:
    """Small BM25 fallback used when rank-bm25 is not installed."""

    def __init__(self, corpus: list[list[str]], *, k1: float = 1.5, b: float = 0.75):
        self.corpus = corpus
        self.k1 = k1
        self.b = b
        self.doc_count = len(corpus)
        self.avgdl = sum(len(doc) for doc in corpus) / self.doc_count if self.doc_count else 0.0
        self.doc_freq: Counter[str] = Counter()
        self.term_freqs: list[Counter[str]] = []
        for doc in corpus:
            counts = Counter(doc)
            self.term_freqs.append(counts)
            self.doc_freq.update(counts.keys())

    def get_scores(self, query_tokens: Iterable[str]) -> list[float]:
        scores: list[float] = []
        for doc, counts in zip(self.corpus, self.term_freqs):
            doc_len = len(doc) or 1
            score = 0.0
            for token in query_tokens:
                tf = counts.get(token, 0)
                if tf == 0:
                    continue
                df = self.doc_freq.get(token, 0)
                idf = math.log(1 + (self.doc_count - df + 0.5) / (df + 0.5))
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1))
                score += idf * (tf * (self.k1 + 1)) / denom
            scores.append(score)
        return scores


class KeywordSearchIndex:
    """In-memory BM25 index reconstructed from a persisted corpus."""

    def __init__(self, documents: list[RAGDocument], tokenized_corpus: list[list[str]]):
        self.documents = documents
        self.tokenized_corpus = tokenized_corpus
        try:
            from rank_bm25 import BM25Okapi

            self.bm25 = BM25Okapi(tokenized_corpus)
        except ModuleNotFoundError:
            self.bm25 = SimpleBM25(tokenized_corpus)

    def search(self, query: str, *, top_k: int = 20, category: Optional[str] = None) -> list[RetrievalCandidate]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        raw_scores = list(self.bm25.get_scores(query_tokens))
        positive_scores = [float(score) for score in raw_scores if score and score > 0]
        max_score = max(positive_scores) if positive_scores else 1.0
        ranked_indexes = sorted(range(len(raw_scores)), key=lambda idx: raw_scores[idx], reverse=True)

        matches: list[RetrievalCandidate] = []
        for index in ranked_indexes:
            score = float(raw_scores[index])
            if score <= 0:
                continue
            document = self.documents[index]
            if category and document.category != category:
                continue
            matches.append(
                RetrievalCandidate(
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
                    sparse_score=min(1.0, score / max_score),
                    sources=["bm25"],
                )
            )
            if len(matches) >= top_k:
                break
        return matches


def build_keyword_index(documents: list[RAGDocument], path: str | Path | None = None) -> Path:
    """Persist BM25 corpus inputs; BM25 itself is rebuilt when loaded."""
    output_path = Path(path or settings.BM25_INDEX_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tokenized_corpus = [tokenize(f"{doc.category} {doc.question} {doc.text}") for doc in documents]
    payload = {
        "documents": [doc.model_dump() for doc in documents],
        "tokenized_corpus": tokenized_corpus,
    }
    with output_path.open("wb") as fp:
        pickle.dump(payload, fp)
    return output_path


def load_keyword_index(path: str | Path | None = None) -> KeywordSearchIndex:
    input_path = Path(path or settings.BM25_INDEX_PATH)
    with input_path.open("rb") as fp:
        payload = pickle.load(fp)
    documents = [RAGDocument.model_validate(item) for item in payload["documents"]]
    return KeywordSearchIndex(documents, payload["tokenized_corpus"])


def search_keyword_index(
    query: str,
    *,
    top_k: int = 20,
    category: Optional[str] = None,
    path: str | Path | None = None,
) -> list[RetrievalCandidate]:
    index = load_keyword_index(path)
    return index.search(query, top_k=top_k, category=category)
