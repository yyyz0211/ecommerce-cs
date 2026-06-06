"""Rule-based query understanding before RAG retrieval."""

from __future__ import annotations

import re

from app.rag.schemas import QueryAnalysis


CATEGORY_KEYWORDS = {
    "售后政策": (
        "退货",
        "退款",
        "换货",
        "售后",
        "返修",
        "保修",
        "拒保",
        "七天无理由",
        "质保",
        "维修",
        "上门取件",
    ),
    "物流配送": (
        "物流",
        "配送",
        "发货",
        "签收",
        "拒收",
        "运费",
        "快递",
        "自提",
        "送达",
        "运输",
        "送货",
        "收货",
    ),
    "支付发票": (
        "支付",
        "付款",
        "白条",
        "发票",
        "开票",
        "对公",
        "转账",
        "货到付款",
        "分期",
        "京东卡",
        "京东E卡",
    ),
    "账户管理": (
        "账号",
        "账户",
        "密码",
        "登录",
        "登陆",
        "实名",
        "认证",
        "手机号",
        "安全",
        "会员",
        "plus",
        "PLUS",
    ),
}

DOMAIN_TERMS = (
    "七天无理由",
    "上门取件",
    "货到付款",
    "京东E卡",
    "京东卡",
    "PLUS会员",
    "订单",
    "生鲜",
    "拒收",
    "签收",
    "退货",
    "换货",
    "退款",
    "售后",
    "发票",
    "开票",
    "物流",
    "运费",
    "白条",
)

BUSINESS_TOOL_TERMS = ("我的订单", "订单号", "订单", "物流单号", "快递单号", "售后单", "申请售后")


def normalize_query(query: str) -> str:
    """Normalize punctuation/spacing while keeping Chinese text intact."""
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", query.strip())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def infer_category(query: str) -> str | None:
    """Infer a JD help-center category with transparent keyword voting."""
    query_lower = query.lower()
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in query_lower:
                # Longer domain phrases are more intentional than single words.
                score += 2 if len(keyword) >= 4 else 1
        scores[category] = score
    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score > 0 else None


def extract_keywords(query: str) -> list[str]:
    """Extract stable retrieval keywords from domain terms and alphanumeric spans."""
    found: list[str] = []
    query_lower = query.lower()
    for term in DOMAIN_TERMS:
        if term.lower() in query_lower and term not in found:
            found.append(term)

    for token in re.findall(r"[A-Za-z0-9_]{2,}", query):
        if token not in found:
            found.append(token)
    return found


def needs_business_tool(query: str) -> bool:
    """Detect queries that likely need order/account tools in addition to RAG."""
    query_lower = query.lower()
    if re.search(r"\b\d{8,}\b", query):
        return True
    return any(term.lower() in query_lower for term in BUSINESS_TOOL_TERMS)


def analyze_query(query: str, *, category: str | None = None) -> QueryAnalysis:
    """Build deterministic query analysis for the first RAG version.

    This is the future LLM rewrite boundary: a model can later fill
    `rewrite_query` or enrich `keywords`, while the rest of the pipeline keeps
    the same contract.
    """
    normalized = normalize_query(query)
    inferred_category = category or infer_category(normalized)
    keywords = extract_keywords(normalized)
    return QueryAnalysis(
        raw_query=query,
        normalized_query=normalized,
        category=inferred_category,
        keywords=keywords,
        needs_business_tool=needs_business_tool(normalized),
        rewrite_query=None,
    )
