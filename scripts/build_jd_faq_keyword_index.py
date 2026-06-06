"""Build the local BM25 keyword index for JD FAQ RAG.

Example:
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
from app.rag.keyword_store import build_keyword_index
from app.rag.loader import load_documents, load_faq_documents

DEFAULT_CLEAN_INPUT = Path("data/jd_faq_clean.jsonl")
DEFAULT_CHUNKS_INPUT = Path("data/jd_faq_chunks.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build JD FAQ BM25 keyword index.")
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
        raise SystemExit("No documents loaded for BM25 index")

    # Persisting both FAQ-level and chunk-level records lets sparse recall catch
    # exact policy titles and exact evidence snippets in one inexpensive index.
    output_path = build_keyword_index(documents, args.output)
    print(f"Done. bm25_index={output_path} documents={len(documents)}")


if __name__ == "__main__":
    main()
