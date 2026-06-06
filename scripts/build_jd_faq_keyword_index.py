"""为京东 FAQ RAG 构建本地 BM25 关键词索引。

示例：
    python3 scripts/build_jd_faq_keyword_index.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.rag.indexing.keyword_store import build_keyword_index
from app.rag.indexing.loader import load_documents, load_faq_documents

DEFAULT_CLEAN_INPUT = Path("data/jd_faq_clean.jsonl")
DEFAULT_CHUNKS_INPUT = Path("data/jd_faq_chunks.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建京东 FAQ BM25 关键词索引。")
    parser.add_argument("--clean-input", type=Path, default=DEFAULT_CLEAN_INPUT)
    parser.add_argument("--chunks-input", type=Path, default=DEFAULT_CHUNKS_INPUT)
    parser.add_argument("--output", type=Path, default=Path(settings.BM25_INDEX_PATH))
    parser.add_argument("--only", choices=("all", "docs", "chunks"), default="all")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    documents = []

    if args.only in ("all", "docs"):
        documents.extend(load_faq_documents(args.clean_input))
    if args.only in ("all", "chunks"):
        documents.extend(load_documents(args.chunks_input))
    if not documents:
        raise SystemExit("未加载到可构建 BM25 索引的文档")

    # 同时持久化 FAQ 级别和 chunk 级别记录，让稀疏召回能在一个低成本索引中
    # 命中精确政策标题和精确证据片段。
    output_path = build_keyword_index(documents, args.output)
    print(f"完成。bm25_index={output_path} documents={len(documents)}")


if __name__ == "__main__":
    main()
