"""京东 FAQ 检索使用的中文 BM25 关键词索引。"""

from __future__ import annotations

import math
import pickle
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Union

from app.config import settings
from app.rag.indexing.keyword_vocabulary import (
    derive_protected_terms,
    load_keyword_vocabulary,
    map_query_to_keywords,
)
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
    "我",
    "想",
    "一下",
    "现在",
    "到底",
    "能",
    "用",
    "哪些",
    "在",
    "哪里",
    "这个",
    "那个",
    "之前",
    "之后",
    "一般",
    "为什么",
    "还",
    "付",
    "不了",
    "行吗",
    "都行",
    "会",
    "到",
    "没到",
    "账",
}


@lru_cache(maxsize=8)
def get_protected_terms(path: Optional[str] = None) -> tuple[str, ...]:
    """读取词库并派生 jieba 保护词，BM25 只消费派生结果。

    这里加缓存是因为分词会被频繁调用，词库文件不需要每次 query 都重新读取。
    如果测试或脚本临时切换 KEYWORD_VOCAB_PATH，需要手动 cache_clear。
    """
    vocabulary = load_keyword_vocabulary(path)
    return derive_protected_terms(vocabulary)


def _load_jieba():
    try:
        import jieba
    except ModuleNotFoundError:
        return None
    for term in get_protected_terms():
        # 领域短语必须强制加入词典，否则“七天无理由/货到付款”等会被切碎。
        jieba.add_word(term, freq=200000)
    return jieba


def _fallback_tokens(text: str) -> list[str]:
    # 没安装 jieba 时的兜底切分方式。
    # 它不如 jieba 精细，但会优先识别词库中的业务短语，保证索引还能构建。
    tokens: list[str] = []
    for term in get_protected_terms():
        if term in text:
            tokens.append(term)
    tokens.extend(re.findall(r"[A-Za-z0-9_]{2,}", text))
    tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return tokens


def tokenize(text: str) -> list[str]:
    """为 BM25 分词，并保护领域短语不被切碎。"""
    normalized = re.sub(r"\s+", " ", text.strip())
    jieba = _load_jieba()
    raw_tokens = jieba.lcut(normalized) if jieba else _fallback_tokens(normalized)

    # 先把命中的业务短语直接放进 token 列表。
    # 这样即使 jieba 后面把“修改支付密码”切成“修改/支付密码”，
    # BM25 里仍然会有完整的“修改支付密码”可用于精确匹配。
    tokens: list[str] = []
    seen_domain_terms = [term for term in get_protected_terms() if term in normalized]
    for term in seen_domain_terms:
        tokens.append(term)

    # 再追加 jieba 的普通分词结果，并过滤掉没有检索价值的停用词。
    # STOPWORDS 只处理工程噪声，不承担语义理解职责。
    for token in raw_tokens:
        token = token.strip()
        if not token or token in STOPWORDS:
            continue
        if len(token) == 1 and not token.isalnum():
            continue
        tokens.append(token)
    return tokens


def tokenize_query(query: str) -> list[str]:
    """BM25 查询分词，并追加受控词表中的标准关键词。"""
    vocabulary = load_keyword_vocabulary()
    # query 侧同时使用两类 token：
    # 1. 用户原话分词，比如“退款”“到账”
    # 2. 词库映射出的标准关键词，比如“退款时效”
    # 这样可以同时覆盖字面匹配和受控关键词匹配。
    return [*tokenize(query), *map_query_to_keywords(query, vocabulary)]

def _weighted_tokens(text: str, weight: int) -> list[str]:
    # BM25 没有“字段权重”参数，这里用重复 token 的方式实现。
    # 例如标题权重 5，等价于标题里的词在文档 token 中出现 5 次。
    return tokenize(text) * max(1, weight)

def tokenize_document(document: RAGDocument) -> list[str]:
    """为 BM25 构建带字段权重的文档 token。
    标题和受控关键词比正文更能表达 FAQ 主意图，因此重复写入 token 序列。
    """
    tokens: list[str] = []
    # 分类是弱信号：能帮助区分“支付密码”属于账户管理还是支付发票。
    tokens.extend(_weighted_tokens(document.category, 2))
    # FAQ 标题通常就是用户问题的标准表达，因此权重最高。
    tokens.extend(_weighted_tokens(document.question, 5))
    if document.section_title:
        # chunk 的小节标题比正文更聚焦，但通常不如 FAQ 标题稳定。
        tokens.extend(_weighted_tokens(document.section_title, 3))
    if document.keywords:
        # 离线打好的 keywords 是标准业务概念，对口语化 query 很关键。
        tokens.extend(_weighted_tokens(" ".join(document.keywords), 4))
    # 正文保留最低权重，避免长答案里的大量泛词压过标题和关键词。
    tokens.extend(tokenize(document.text))
    return tokens

class SimpleBM25:
    """rank-bm25 未安装时使用的轻量 BM25 兜底实现。"""

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
    """从持久化语料重建出来的内存 BM25 索引。"""

    def __init__(self, documents: list[RAGDocument], tokenized_corpus: list[list[str]]):
        self.documents = documents
        self.tokenized_corpus = tokenized_corpus
        try:
            from rank_bm25 import BM25Okapi

            self.bm25 = BM25Okapi(tokenized_corpus)
        except ModuleNotFoundError:
            self.bm25 = SimpleBM25(tokenized_corpus)

    def search(self, query: str, *, top_k: int = 20, category: Optional[str] = None) -> list[RetrievalCandidate]:
        query_tokens = tokenize_query(query)
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
                    keywords=document.keywords,
                    keyword_version=document.keyword_version,
                    sparse_score=min(1.0, score / max_score),
                    sources=["bm25"],
                )
            )
            if len(matches) >= top_k:
                break
        return matches


def build_keyword_index(documents: list[RAGDocument], path: Optional[Union[str, Path]] = None) -> Path:
    """持久化 BM25 所需语料；真正的 BM25 对象在加载时重建。"""
    output_path = Path(path or settings.BM25_INDEX_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 持久化的是文档和 token 序列，不直接 pickle BM25 对象。
    # 这样 rank_bm25 是否安装、版本是否变化，都不会影响索引文件的可读性。
    tokenized_corpus = [tokenize_document(doc) for doc in documents]
    payload = {
        "documents": [doc.model_dump() for doc in documents],
        "tokenized_corpus": tokenized_corpus,
    }
    with output_path.open("wb") as fp:
        pickle.dump(payload, fp)
    return output_path


def load_keyword_index(path: Optional[Union[str, Path]] = None) -> KeywordSearchIndex:
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
    path: Optional[Union[str, Path]] = None,
) -> list[RetrievalCandidate]:
    index = load_keyword_index(path)
    return index.search(query, top_k=top_k, category=category)
