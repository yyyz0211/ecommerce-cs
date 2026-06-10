"""关键词词库管理。

本模块只负责“词库”这一层：
- 加载人工/LLM 审核后的正式关键词词库。
- 在词库缺失时回退到内置规则基线。
- 从词库派生 jieba 需要保护的业务词。
- 用词库把用户 query 映射到标准关键词。

BM25 分词、建索引、检索逻辑不要放在这里。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.rag.indexing.keyword_taxonomy import (
    BASE_KEYWORD_RULES,
    KEYWORD_VERSION,
    extract_query_keywords,
    extract_query_keywords_from_vocabulary,
)
from app.rag.planning.analyzer import DOMAIN_TERMS


def rules_to_vocabulary() -> dict[str, Any]:
    """把内置规则转换成标准词库结构，作为离线词库缺失时的兜底。

    正常链路应该读取 data/jd_faq_keyword_vocab.json。
    这里保留兜底，是为了避免词库文件还没生成时应用直接启动失败。
    """
    return {
        "version": KEYWORD_VERSION,
        "keywords": [
            {
                "id": rule.id,
                "canonical": rule.canonical,
                "category": rule.category,
                "aliases": list(rule.aliases),
                "boost": rule.boost,
            }
            for rule in BASE_KEYWORD_RULES
        ],
    }


def _is_valid_vocabulary(value: Any) -> bool:
    """只做最小结构校验；更严格的质量审核放在离线生成阶段。

    运行时只关心词库能否被消费，不在这里判断关键词质量。
    关键词是否合理，应通过离线 review 文件和评测结果判断。
    """
    return isinstance(value, dict) and isinstance(value.get("keywords"), list)


@lru_cache(maxsize=8)
def load_keyword_vocabulary(path: Optional[str] = None) -> dict[str, Any]:
    """加载正式关键词词库；文件不可用时返回内置规则基线。

    这是线上检索读取关键词词库的唯一入口。
    这样 BM25、query 扩展、jieba 保护词都使用同一份词库，避免多处写死规则。
    """
    vocab_path = Path(path or settings.KEYWORD_VOCAB_PATH)
    if not vocab_path.exists():
        return rules_to_vocabulary()

    with vocab_path.open("r", encoding="utf-8") as fp:
        vocabulary = json.load(fp)

    if not _is_valid_vocabulary(vocabulary):
        return rules_to_vocabulary()
    return vocabulary


def derive_protected_terms(vocabulary: dict[str, Any]) -> tuple[str, ...]:
    """从词库派生分词保护词，包含标准词、别名和基础领域词。

    这些词会被加入 jieba 词典，目的是让“支付密码”“七天无理由”
    这类业务短语尽量作为一个整体 token 进入 BM25。
    """
    terms: list[str] = [*DOMAIN_TERMS]
    for item in vocabulary.get("keywords", []):
        if not isinstance(item, dict):
            continue
        terms.append(str(item.get("canonical") or ""))
        terms.extend(str(alias or "") for alias in item.get("aliases") or [])
    return tuple(term for term in dict.fromkeys(terms) if term)


def map_query_to_keywords(query: str, vocabulary: dict[str, Any]) -> list[str]:
    """用正式词库映射 query，并用内置规则补足常见口语别名。

    例子：
    “我想改一下支付密码”会额外补出“修改支付密码”“支付密码”。
    这些标准关键词会和 query 分词一起进入 BM25，提高口语化问题的召回率。
    """
    keywords = [
        *extract_query_keywords_from_vocabulary(query, vocabulary),
        *extract_query_keywords(query),
    ]
    return list(dict.fromkeys(keywords))
