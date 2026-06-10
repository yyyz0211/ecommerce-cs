"""使用受控关键词词库给京东 FAQ 和 chunk 打 keywords。

示例：
    python3 scripts/annotate_jd_faq_keywords.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.rag.indexing.keyword_taxonomy import annotate_chunk_keywords, annotate_record_keywords

DEFAULT_CLEAN_INPUT = Path("data/jd_faq_clean.jsonl")
DEFAULT_CHUNKS_INPUT = Path("data/jd_faq_chunks.jsonl")
DEFAULT_VOCAB = Path("data/jd_faq_keyword_vocab.json")
DEFAULT_CLEAN_OUTPUT = Path("data/jd_faq_clean_keywords.jsonl")
DEFAULT_CHUNKS_OUTPUT = Path("data/jd_faq_chunks_keywords.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="给京东 FAQ 数据写入 keywords 字段。")
    parser.add_argument("--clean-input", type=Path, default=DEFAULT_CLEAN_INPUT)
    parser.add_argument("--chunks-input", type=Path, default=DEFAULT_CHUNKS_INPUT)
    parser.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB)
    parser.add_argument("--clean-output", type=Path, default=DEFAULT_CLEAN_OUTPUT)
    parser.add_argument("--chunks-output", type=Path, default=DEFAULT_CHUNKS_OUTPUT)
    parser.add_argument("--max-keywords", type=int, default=8)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    args = parse_args()
    vocabulary = load_json(args.vocab)

    clean_rows = load_jsonl(args.clean_input)
    # FAQ 级别先打 keywords。
    # 这份输出后续会用于 FAQ 级别向量索引和 BM25 FAQ 文档索引。
    annotated_clean = [
        annotate_record_keywords(row, vocabulary, max_keywords=args.max_keywords)
        if row.get("kb_candidate") is not False
        else {**row, "keywords": [], "keyword_version": vocabulary.get("version")}
        for row in clean_rows
    ]
    clean_count = write_jsonl(args.clean_output, annotated_clean)

    # chunk 级别再打 keywords，并继承所属 FAQ 的关键词。
    # 原因是 chunk 可能只包含答案中的一小段，局部文本不一定出现完整主题词。
    faq_keywords = {str(row.get("id")): list(row.get("keywords") or []) for row in annotated_clean}
    chunk_rows = load_jsonl(args.chunks_input)
    annotated_chunks = [
        annotate_chunk_keywords(
            row,
            vocabulary,
            faq_keywords=faq_keywords.get(str(row.get("faq_id")), []),
            max_keywords=args.max_keywords,
        )
        for row in chunk_rows
    ]
    chunk_count = write_jsonl(args.chunks_output, annotated_chunks)

    clean_with_keywords = sum(1 for row in annotated_clean if row.get("keywords"))
    chunks_with_keywords = sum(1 for row in annotated_chunks if row.get("keywords"))
    print(
        "完成。"
        f"clean_output={args.clean_output} rows={clean_count} with_keywords={clean_with_keywords}; "
        f"chunks_output={args.chunks_output} rows={chunk_count} with_keywords={chunks_with_keywords}"
    )


if __name__ == "__main__":
    main()
