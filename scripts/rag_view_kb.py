"""在 CLI 中用表格查看京东 FAQ 知识库内容。

示例：
    python3 scripts/rag_view_kb.py
    python3 scripts/rag_view_kb.py --category 售后政策 --limit 20
    python3 scripts/rag_view_kb.py --search "生鲜 拒收" --show-answer
    python3 scripts/rag_view_kb.py --id 39813b4df2ad22a7
    python3 scripts/rag_view_kb.py --include-rejected --stats-only
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = ROOT_DIR / "data" / "jd_faq_clean.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用表格查看京东 FAQ 知识库。")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH), help="知识库 JSONL 路径。")
    parser.add_argument("--category", default=None, help="按分类过滤。")
    parser.add_argument("--search", default=None, help="按关键词过滤，多个词用空格分隔。")
    parser.add_argument("--id", dest="faq_id", default=None, help="查看指定 FAQ ID 的完整内容。")
    parser.add_argument("--limit", type=int, default=10, help="最多显示多少条 FAQ。")
    parser.add_argument("--show-answer", action="store_true", help="在列表中显示答案摘要。")
    parser.add_argument("--answer-chars", type=int, default=240, help="答案摘要最大字符数。")
    parser.add_argument("--stats-only", action="store_true", help="只显示统计信息。")
    parser.add_argument("--include-rejected", action="store_true", help="包含被标记为不适合入库的清洗记录。")
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} 不是合法 JSON: {exc}") from exc
    return rows


def clip(text: str | None, max_chars: int) -> str:
    """截断长文本，避免终端表格失去可读性。"""
    value = " ".join((text or "").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def print_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> None:
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        print("| " + " | ".join(escape_md(value) for value in row) + " |")


def print_stats(rows: list[dict[str, Any]]) -> None:
    by_category = Counter(row.get("category") or "未分类" for row in rows)
    by_source = Counter(row.get("source") or "未知来源" for row in rows)
    answer_lengths = [len(row.get("answer") or row.get("text") or "") for row in rows]

    print("# 知识库统计")
    print()
    print_table(
        ["指标", "值"],
        [
            ["FAQ 总数", len(rows)],
            ["分类数", len(by_category)],
            ["来源数", len(by_source)],
            ["平均答案长度", round(sum(answer_lengths) / max(len(answer_lengths), 1), 1)],
            ["最长答案长度", max(answer_lengths, default=0)],
        ],
    )
    print()
    print("## 分类分布")
    print()
    print_table(["分类", "FAQ 数量"], by_category.most_common())
    print()


def print_faq_detail(row: dict[str, Any]) -> None:
    print(f"# {row.get('question')}")
    print()
    print_table(
        ["字段", "值"],
        [
            ["FAQ ID", row.get("id")],
            ["分类", row.get("category")],
            ["来源", row.get("source")],
            ["URL", row.get("url")],
            ["KB 候选", row.get("kb_candidate", True)],
            ["过滤原因", row.get("reject_reason") or "-"],
            ["答案长度", len(row.get("answer") or row.get("text") or "")],
        ],
    )
    print()
    print("## 答案")
    print()
    print(row.get("answer") or row.get("text") or "")


def filter_rows(rows: list[dict[str, Any]], *, category: str | None, search: str | None) -> list[dict[str, Any]]:
    filtered = rows
    if category:
        filtered = [row for row in filtered if row.get("category") == category]
    if search:
        keywords = [item for item in search.lower().split() if item]

        def matched(row: dict[str, Any]) -> bool:
            haystack = f"{row.get('question', '')} {row.get('answer', '')} {row.get('text', '')}".lower()
            return all(keyword in haystack for keyword in keywords)

        filtered = [row for row in filtered if matched(row)]
    return filtered


def print_rows(rows: list[dict[str, Any]], *, limit: int, show_answer: bool, answer_chars: int) -> None:
    headers = ["序号", "FAQ ID", "分类", "标题", "答案长度", "URL"]
    table_rows: list[list[Any]] = []
    if show_answer:
        headers.append("答案摘要")

    for index, row in enumerate(rows[:limit], start=1):
        item = [
            index,
            row.get("id"),
            row.get("category"),
            clip(row.get("question"), 60),
            len(row.get("answer") or row.get("text") or ""),
            row.get("url"),
        ]
        if show_answer:
            item.append(clip(row.get("answer") or row.get("text"), answer_chars))
        table_rows.append(item)

    print_table(headers, table_rows)


def print_category_samples(rows: list[dict[str, Any]], limit: int) -> None:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[row.get("category") or "未分类"].append(row)

    for category, items in sorted(by_category.items()):
        print(f"## {category}")
        print()
        print_rows(items, limit=limit, show_answer=False, answer_chars=0)
        print()


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    rows = load_rows(data_path)
    if not args.include_rejected:
        # RAG 索引构建时也会过滤 kb_candidate=false 的记录，这里默认和索引口径一致。
        rows = [row for row in rows if row.get("kb_candidate") is not False]

    if args.faq_id:
        for row in rows:
            if row.get("id") == args.faq_id:
                print_faq_detail(row)
                return
        raise SystemExit(f"未找到 FAQ ID: {args.faq_id}")

    filtered = filter_rows(rows, category=args.category, search=args.search)
    print_stats(filtered)
    if args.stats_only:
        return

    if args.category or args.search:
        print("# FAQ 列表")
        print()
        print_rows(filtered, limit=args.limit, show_answer=args.show_answer, answer_chars=args.answer_chars)
        return

    print("# 分类样例")
    print()
    print_category_samples(filtered, limit=max(1, min(args.limit, 5)))


if __name__ == "__main__":
    main()
