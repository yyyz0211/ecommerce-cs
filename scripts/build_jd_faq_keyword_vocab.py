"""根据清洗后的京东 FAQ 数据生成受控关键词词库。

示例：
    python3 scripts/build_jd_faq_keyword_vocab.py
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

from app.rag.indexing.keyword_taxonomy import build_keyword_vocabulary

DEFAULT_INPUT = Path("data/jd_faq_clean.jsonl")
DEFAULT_OUTPUT = Path("data/jd_faq_keyword_vocab.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建京东 FAQ 受控关键词词库。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-doc-count", type=int, default=1, help="至少命中多少条 FAQ 才进入词库。")
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


def main() -> None:
    args = parse_args()
    rows = load_jsonl(args.input)
    vocabulary = build_keyword_vocabulary(rows, min_doc_count=args.min_doc_count)
    vocabulary["source_file"] = str(args.input)
    vocabulary["min_doc_count"] = args.min_doc_count

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(vocabulary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "完成。"
        f"input={args.input} output={args.output} "
        f"documents={vocabulary['document_count']} keywords={vocabulary['keyword_count']}"
    )


if __name__ == "__main__":
    main()
