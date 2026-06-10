"""让 LLM 从 FAQ 数据中统计原始关键词表达。

这一步不生成正式词库，只统计 FAQ 中出现的业务概念表达，允许近义词重复出现。

示例：
    python3 scripts/mine_jd_faq_keyword_expressions_llm.py --dry-run
    python3 scripts/mine_jd_faq_keyword_expressions_llm.py
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
from app.rag.indexing.llm_keyword_mining import normalize_mined_expressions, parse_llm_json

DEFAULT_INPUT = Path("data/jd_faq_clean.jsonl")
DEFAULT_RAW_OUTPUT = Path("data/jd_faq_llm_keyword_expressions_raw.json")
DEFAULT_OUTPUT = Path("data/jd_faq_llm_keyword_expressions.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM 统计京东 FAQ 原始关键词表达。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--category", choices=CATEGORY_ORDER, default=None)
    parser.add_argument("--per-category-limit", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--max-expressions-per-batch", type=int, default=30)
    parser.add_argument("--model", default=settings.LLM_MODEL)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 行无效: {path}:{line_no}: {exc}") from exc
    return rows


def select_rows_for_category(rows: list[dict[str, Any]], category: str, *, limit: int) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if row.get("kb_candidate") is not False and str(row.get("category") or "") == category
    ]
    selected.sort(key=lambda row: (-len(str(row.get("answer") or row.get("text") or "")), str(row.get("question") or "")))
    return selected[:limit]


def batched(items: list[dict[str, Any]], batch_size: int):
    for index in range(0, len(items), batch_size):
        yield index // batch_size + 1, items[index : index + batch_size]


def compact_faq(row: dict[str, Any], *, answer_chars: int = 420) -> dict[str, str]:
    answer = str(row.get("answer") or row.get("text") or "").replace("\n", " ")
    if len(answer) > answer_chars:
        answer = answer[:answer_chars] + "..."
    return {
        "id": str(row.get("id") or ""),
        "question": str(row.get("question") or ""),
        "answer": answer,
    }


def build_expression_mining_prompt(category: str, rows: list[dict[str, Any]], *, max_expressions: int) -> str:
    samples = [compact_faq(row) for row in rows]
    return (
        "你是电商客服 FAQ RAG 系统的关键词分析专家。\n"
        f"请基于“{category}”分类下的真实 FAQ，统计原始表达。\n"
        "这里不要合并近义词，不要生成最终标准词，只抽取用户可能用于检索的业务概念表达。\n"
        "要求：\n"
        "1. 只输出 JSON，不要解释。\n"
        "2. 顶层格式必须是 {\"expressions\": [...]}。\n"
        "3. 每项字段必须包含 text、category、faq_ids。\n"
        "4. text 可以是原文概念或用户可能说法，例如“改支付密码”“退款多久到账”。\n"
        "5. 不要输出“商品/问题/服务/用户/订单”等泛词。\n"
        "6. category 必须严格等于当前分类。\n"
        f"7. 最多输出 {max_expressions} 个表达。\n\n"
        f"FAQ 样本：\n{json.dumps(samples, ensure_ascii=False, indent=2)}"
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
        temperature=0.2,
    )
    return response.choices[0].message.content or "{}"


def main() -> None:
    args = parse_args()
    rows = load_jsonl(args.input)
    categories = [args.category] if args.category else list(CATEGORY_ORDER)
    batches: list[dict[str, Any]] = []

    for category in categories:
        category_rows = select_rows_for_category(rows, category, limit=args.per_category_limit)
        for batch_index, batch_rows in batched(category_rows, args.batch_size):
            prompt = build_expression_mining_prompt(
                category,
                batch_rows,
                max_expressions=args.max_expressions_per_batch,
            )
            batch: dict[str, Any] = {
                "category": category,
                "batch_index": batch_index,
                "faq_count": len(batch_rows),
                "faq_ids": [str(row.get("id") or "") for row in batch_rows],
                "prompt": prompt if args.dry_run else None,
            }
            if not args.dry_run:
                raw_response = call_llm(prompt, model=args.model)
                batch["raw_response"] = raw_response
                batch["parsed"] = parse_llm_json(raw_response)
            batches.append(batch)

    raw_payload = {
        "version": "jd_faq_llm_keyword_expressions_raw_v1",
        "source_file": str(args.input),
        "model": args.model,
        "dry_run": args.dry_run,
        "batch_count": len(batches),
        "batches": batches,
    }
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.dry_run:
        normalized = normalize_mined_expressions(raw_payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"完成。raw_output={args.raw_output} dry_run={args.dry_run} batches={len(batches)}")


if __name__ == "__main__":
    main()
