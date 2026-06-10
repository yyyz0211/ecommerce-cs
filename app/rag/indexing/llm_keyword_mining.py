"""LLM 关键词统计与归一化。

流程分两步：
1. LLM 从 FAQ 中统计用户表达/业务概念表达。
2. LLM 再把相近表达聚类为标准关键词。

本模块只做 JSON 解析、去噪、合并、对齐现有词库；不直接调用 LLM。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Iterable, Optional

from app.rag.indexing.keyword_taxonomy import CATEGORY_ORDER


EXPRESSION_VERSION = "jd_faq_llm_keyword_expressions_v1"
VOCAB_VERSION = "jd_faq_keywords_llm_v1"
CATEGORY_SLUGS = {
    "售后政策": "after_sale",
    "物流配送": "logistics",
    "支付发票": "payment_invoice",
    "账户管理": "account",
}
GENERIC_TERMS = {
    "京东",
    "商品",
    "问题",
    "服务",
    "用户",
    "客户",
    "订单",
    "信息",
    "规则",
    "说明",
    "帮助",
    "使用",
    "操作",
}


def parse_llm_json(content: str) -> Any:
    """解析 LLM JSON，兼容 ```json 代码块。

    很多模型即使被要求“只输出 JSON”，也可能包一层 Markdown code fence。
    这里统一剥掉 fence，避免后续 json.loads 失败。
    """
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"^[\s,，、。；;：:]+|[\s,，、。；;：:]+$", "", text)


def _normalize_key(value: Any) -> str:
    # 用于去重和对齐，不用于展示。
    # 例如“京东 E 卡”和“京东E卡”会被归一成更接近的 key。
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").lower())


def _ordered_unique(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = _clean_text(value)
        key = _normalize_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _is_generic(text: str) -> bool:
    # LLM 很容易产出“商品/问题/服务”这类泛词。
    # 这些词覆盖面太大，进入关键词词库会降低检索区分度。
    key = _normalize_key(text)
    return not key or key in {_normalize_key(term) for term in GENERIC_TERMS} or len(text) < 2


def _iter_expressions(payload: Any) -> Iterable[dict[str, Any]]:
    """兼容多种 LLM 原始输出结构，统一迭代表达项。

    dry-run、批量调用、单次调用产生的 JSON 外层结构可能不同。
    这里集中做适配，后面的 normalize_mined_expressions 就可以只关心表达本身。
    """
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if not isinstance(payload, dict):
        return

    values = payload.get("expressions") or payload.get("items")
    if isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                yield item

    batches = payload.get("batches")
    if isinstance(batches, list):
        for batch in batches:
            if not isinstance(batch, dict):
                continue
            category = batch.get("category")
            parsed = batch.get("parsed") if isinstance(batch.get("parsed"), dict) else batch
            values = parsed.get("expressions") or parsed.get("items") or []
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict):
                    yield {**item, "category": item.get("category") or category}


def normalize_mined_expressions(payload: Any) -> dict[str, Any]:
    """合并 LLM 统计出的表达，保留频次和来源 FAQ。

    第一阶段不做同义词合并，只统计“原始表达”。
    这样可以先看到真实数据里用户/FAQ 都有哪些说法，再进入第二阶段聚类归一化。
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    for item in _iter_expressions(payload):
        text = _clean_text(item.get("text") or item.get("expression") or item.get("keyword"))
        category = _clean_text(item.get("category"))
        faq_ids = _ordered_unique(item.get("faq_ids") or item.get("source_faq_ids") or [])
        if category not in CATEGORY_ORDER:
            rejected.append({"raw": item, "reason": "invalid_category"})
            continue
        if _is_generic(text):
            rejected.append({"raw": item, "reason": "generic_or_empty"})
            continue

        key = (category, text)
        current = merged.get(key)
        if current is None:
            # 第一次看到这个表达时初始化记录；count 代表它被 LLM 反复识别的次数。
            merged[key] = {
                "text": text,
                "category": category,
                "count": 1,
                "faq_ids": faq_ids,
            }
            continue
        current["count"] = int(current["count"]) + 1
        # 来源 FAQ 用于人工审核：看到某个表达时，可以追溯它来自哪些原始 FAQ。
        current["faq_ids"] = _ordered_unique([*current.get("faq_ids", []), *faq_ids])

    category_rank = {category: index for index, category in enumerate(CATEGORY_ORDER)}
    expressions = sorted(
        merged.values(),
        key=lambda item: (
            category_rank.get(item["category"], 99),
            -int(item["count"]),
            item["text"],
        ),
    )
    return {
        "version": EXPRESSION_VERSION,
        "expression_count": len(expressions),
        "rejected_count": len(rejected),
        "expressions": expressions,
        "rejected": rejected,
    }


def _iter_clusters(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if not isinstance(payload, dict):
        return
    values = payload.get("clusters") or payload.get("keywords")
    if isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                yield item


def _existing_lookup(existing_vocabulary: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """把现有词库展开成 term -> keyword 的查找表。

    LLM 聚类可能输出“更改支付密码”，但旧词库里已有“修改支付密码”。
    这里用 canonical 和 aliases 一起对齐，尽量复用已有关键词 ID。
    """
    lookup: dict[str, dict[str, Any]] = {}
    if not existing_vocabulary:
        return lookup
    for item in existing_vocabulary.get("keywords", []):
        for term in [item.get("canonical"), *(item.get("aliases") or [])]:
            key = _normalize_key(term)
            if key:
                lookup[key] = item
    return lookup


def _keyword_id(category: str, canonical: str) -> str:
    # 新增 LLM 关键词没有人工维护的稳定 ID，因此用 category+canonical 生成短 hash。
    # canonical 不变时 ID 稳定；canonical 改了，说明概念也被调整了。
    digest = hashlib.sha1(f"{category}:{canonical}".encode("utf-8")).hexdigest()[:10]
    return f"llm.{CATEGORY_SLUGS.get(category, 'general')}.{digest}"


def normalize_keyword_clusters(
    payload: Any,
    *,
    existing_vocabulary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """把 LLM 聚类结果归一化成正式词库候选结构。

    第二阶段会把“改支付密码/更改支付密码/付款密码怎么改”合并成一个 canonical。
    如果能和已有词库对齐，就复用已有 canonical 和 id；否则标记为新增词，供人工审核。
    """
    existing = _existing_lookup(existing_vocabulary)
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    for item in _iter_clusters(payload):
        canonical = _clean_text(item.get("canonical") or item.get("keyword") or item.get("name"))
        category = _clean_text(item.get("category"))
        aliases = _ordered_unique(item.get("aliases") or item.get("synonyms") or [])
        source_expressions = _ordered_unique(item.get("source_expressions") or item.get("expressions") or [])
        description = _clean_text(item.get("description"))

        if category not in CATEGORY_ORDER:
            rejected.append({"raw": item, "reason": "invalid_category"})
            continue
        if _is_generic(canonical):
            rejected.append({"raw": item, "reason": "generic_or_empty"})
            continue

        matched_existing = None
        for term in [canonical, *aliases, *source_expressions]:
            matched_existing = existing.get(_normalize_key(term))
            if matched_existing:
                break

        existing_keyword = matched_existing is not None
        if matched_existing:
            # 对齐已有词时，以已有 canonical 为准，避免同义词越来越分散。
            raw_canonical = canonical
            canonical = str(matched_existing["canonical"])
            category = str(matched_existing["category"])
            aliases = _ordered_unique(
                [
                    *(matched_existing.get("aliases") or []),
                    raw_canonical if _normalize_key(raw_canonical) != _normalize_key(canonical) else "",
                    *aliases,
                ]
            )

        key = (category, canonical)
        current = merged.get(key)
        if current is None:
            # 首次出现该标准词时创建词库项；后续同 canonical 的 cluster 会继续合并 aliases。
            merged[key] = {
                "id": matched_existing.get("id") if matched_existing else _keyword_id(category, canonical),
                "canonical": canonical,
                "category": category,
                "aliases": [alias for alias in aliases if _normalize_key(alias) != _normalize_key(canonical)],
                "description": description,
                "source_expressions": source_expressions,
                "source": "llm_cluster",
                "existing_keyword": existing_keyword,
                "boost": float(matched_existing.get("boost", 1.0)) if matched_existing else 1.0,
            }
            continue

        current["aliases"] = _ordered_unique([*current.get("aliases", []), *aliases])
        current["source_expressions"] = _ordered_unique(
            [*current.get("source_expressions", []), *source_expressions]
        )
        current["existing_keyword"] = bool(current.get("existing_keyword") or existing_keyword)
        if not current.get("description") and description:
            current["description"] = description

    category_rank = {category: index for index, category in enumerate(CATEGORY_ORDER)}
    keywords = sorted(
        merged.values(),
        key=lambda item: (category_rank.get(item["category"], 99), item["canonical"]),
    )
    return {
        "version": VOCAB_VERSION,
        "keyword_count": len(keywords),
        "new_keyword_count": sum(1 for item in keywords if not item["existing_keyword"]),
        "existing_keyword_count": sum(1 for item in keywords if item["existing_keyword"]),
        "rejected_count": len(rejected),
        "keywords": keywords,
        "rejected": rejected,
    }
