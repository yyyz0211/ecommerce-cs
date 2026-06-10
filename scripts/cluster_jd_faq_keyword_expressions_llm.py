"""让 LLM 将原始表达聚类为标准关键词词库。

输入来自 scripts/mine_jd_faq_keyword_expressions_llm.py 的表达统计结果。

示例：
    python3 scripts/cluster_jd_faq_keyword_expressions_llm.py --dry-run
    python3 scripts/cluster_jd_faq_keyword_expressions_llm.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.rag.indexing.keyword_taxonomy import CATEGORY_ORDER
from app.rag.indexing.llm_keyword_mining import normalize_keyword_clusters, parse_llm_json

DEFAULT_INPUT = Path("data/jd_faq_llm_keyword_expressions.json")
DEFAULT_EXISTING_VOCAB = Path("data/jd_faq_keyword_vocab.json")
DEFAULT_RAW_OUTPUT = Path("data/jd_faq_keyword_vocab_llm_raw.json")
DEFAULT_OUTPUT = Path("data/jd_faq_keyword_vocab_llm.json")
DEFAULT_REVIEW_OUTPUT = Path("data/jd_faq_keyword_vocab_llm_review.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM 将原始表达聚类为标准关键词词库。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--existing-vocab", type=Path, default=DEFAULT_EXISTING_VOCAB)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW_OUTPUT)
    parser.add_argument("--category", choices=CATEGORY_ORDER, default=None)
    parser.add_argument("--max-expressions-per-category", type=int, default=120)
    parser.add_argument("--max-keywords-per-category", type=int, default=40)
    parser.add_argument("--model", default=settings.LLM_MODEL)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def select_expressions_for_category(
    expressions: list[dict[str, Any]],
    category: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    selected = [item for item in expressions if str(item.get("category") or "") == category]
    selected.sort(key=lambda item: (-int(item.get("count") or 0), str(item.get("text") or "")))
    return selected[:limit]


def build_keyword_clustering_prompt(category: str, expressions: list[dict[str, Any]], *, max_keywords: int) -> str:
    compact = [
        {
            "text": item.get("text"),
            "count": item.get("count"),
            "faq_ids": list(item.get("faq_ids") or [])[:5],
        }
        for item in expressions
    ]
    return (
        "你是电商客服 FAQ RAG 系统的关键词词库设计专家。\n"
        f"请把“{category}”分类下的原始表达合并意思相近的说法，归一化为标准关键词。\n"
        "要求：\n"
        "1. 只输出 JSON，不要解释。\n"
        "2. 顶层格式必须是 {\"clusters\": [...]}。\n"
        "3. 每个 cluster 必须包含 canonical、category、aliases、source_expressions、description。\n"
        "4. canonical 是标准业务概念词，例如“修改支付密码”。\n"
        "5. aliases 放入被合并的近义表达。\n"
        "6. source_expressions 必须来自输入表达列表。\n"
        "7. 不要输出“商品/问题/服务/用户/订单”等泛词。\n"
        "8. category 必须严格等于当前分类。\n"
        f"9. 最多输出 {max_keywords} 个标准关键词。\n\n"
        f"原始表达：\n{json.dumps(compact, ensure_ascii=False, indent=2)}"
    )


def call_llm(prompt: str, *, model: str) -> str:
    from openai import OpenAI

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("未配置 OPENAI_API_KEY，无法调用 LLM。")
    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你只输出可解析 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content or "{}"


def _escape_table(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def build_review_markdown(vocab: dict[str, Any]) -> str:
    lines = [
        "# LLM 归一化关键词词库审核表",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 关键词总数 | {vocab.get('keyword_count', 0)} |",
        f"| 已对齐现有词 | {vocab.get('existing_keyword_count', 0)} |",
        f"| 新增关键词 | {vocab.get('new_keyword_count', 0)} |",
        f"| 被拒绝项 | {vocab.get('rejected_count', 0)} |",
        "",
        "## 关键词",
        "",
        "| 状态 | 分类 | 标准词 | 同义表达 | 来源表达 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in vocab.get("keywords", []):
        status = "已有" if item.get("existing_keyword") else "新增"
        aliases = "、".join(item.get("aliases") or [])
        sources = "、".join(item.get("source_expressions") or [])
        lines.append(
            f"| {status} | {_escape_table(item.get('category'))} | {_escape_table(item.get('canonical'))} | "
            f"{_escape_table(aliases)} | {_escape_table(sources)} |"
        )
    return "\n".join(lines) + "\n"


def write_keyword_outputs(vocab: dict[str, Any], *, output: Path, review_output: Path) -> None:
    """写入正式词库和审核表；支持不存在的自定义输出目录。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    review_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    review_output.write_text(build_review_markdown(vocab), encoding="utf-8")


def main() -> None:
    args = parse_args()
    expression_payload = load_json(args.input)
    expressions = list(expression_payload.get("expressions") or [])
    categories = [args.category] if args.category else list(CATEGORY_ORDER)
    batches: list[dict[str, Any]] = []

    for category in categories:
        category_expressions = select_expressions_for_category(
            expressions,
            category,
            limit=args.max_expressions_per_category,
        )
        prompt = build_keyword_clustering_prompt(
            category,
            category_expressions,
            max_keywords=args.max_keywords_per_category,
        )
        batch: dict[str, Any] = {
            "category": category,
            "expression_count": len(category_expressions),
            "prompt": prompt if args.dry_run else None,
        }
        if not args.dry_run:
            raw_response = call_llm(prompt, model=args.model)
            batch["raw_response"] = raw_response
            batch["parsed"] = parse_llm_json(raw_response)
        batches.append(batch)

    raw_payload = {
        "version": "jd_faq_keyword_vocab_llm_raw_v1",
        "source_file": str(args.input),
        "model": args.model,
        "dry_run": args.dry_run,
        "batches": batches,
    }
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.dry_run:
        existing = load_json(args.existing_vocab) if args.existing_vocab.exists() else None
        cluster_payload = {
            "clusters": [
                cluster
                for batch in batches
                for cluster in (batch.get("parsed", {}).get("clusters") or [])
            ]
        }
        vocab = normalize_keyword_clusters(cluster_payload, existing_vocabulary=existing)
        write_keyword_outputs(vocab, output=args.output, review_output=args.review_output)

    print(f"完成。raw_output={args.raw_output} dry_run={args.dry_run} batches={len(batches)}")


if __name__ == "__main__":
    main()
