"""Build Chroma indexes from cleaned JD FAQ data.

Prerequisites:
    1. data/jd_faq_clean.jsonl and data/jd_faq_chunks.jsonl exist
    2. chromadb is installed
    3. EMBEDDING_API_KEY / OPENAI_API_KEY is configured

Example:
    python3 scripts/build_jd_faq_chroma.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.rag.embeddings import embed_texts
from app.rag.loader import load_documents, load_faq_documents
from app.rag.vector_store import add_documents, reset_collection

DEFAULT_CLEAN_INPUT = Path("data/jd_faq_clean.jsonl")
DEFAULT_CHUNKS_INPUT = Path("data/jd_faq_chunks.jsonl")


def batched(items, batch_size: int):
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build JD FAQ Chroma indexes.")
    parser.add_argument("--clean-input", type=Path, default=DEFAULT_CLEAN_INPUT)
    parser.add_argument("--chunks-input", "--input", dest="chunks_input", type=Path, default=DEFAULT_CHUNKS_INPUT)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--persist-dir", default=settings.CHROMA_PERSIST_DIR)
    parser.add_argument("--doc-collection", default=settings.CHROMA_DOC_COLLECTION)
    parser.add_argument("--chunk-collection", "--collection", dest="chunk_collection", default=settings.CHROMA_CHUNK_COLLECTION)
    parser.add_argument("--only", choices=("all", "docs", "chunks"), default="all")
    parser.add_argument("--no-reset", action="store_true", help="Append to existing collection instead of recreating it.")
    return parser.parse_args()


def index_documents(label: str, documents, *, collection: str, persist_dir: str, batch_size: int, reset: bool) -> None:
    if not documents:
        raise SystemExit(f"No {label} documents loaded")

    if reset:
        reset_collection(collection, persist_dir)

    total = len(documents)
    indexed = 0
    for batch in batched(documents, batch_size):
        embeddings = embed_texts([doc.text for doc in batch])
        add_documents(batch, embeddings, collection_name=collection, persist_dir=persist_dir)
        indexed += len(batch)
        print(f"Indexed {label} {indexed}/{total}")

    print(f"Done. label={label} collection={collection} persist_dir={persist_dir} documents={total}")


def main() -> None:
    args = parse_args()

    if args.only in ("all", "docs"):
        # FAQ-level documents improve recall when the user asks broad policy questions.
        faq_documents = load_faq_documents(args.clean_input)
        index_documents(
            "faq",
            faq_documents,
            collection=args.doc_collection,
            persist_dir=args.persist_dir,
            batch_size=args.batch_size,
            reset=not args.no_reset,
        )

    if args.only in ("all", "chunks"):
        # Chunk-level documents provide precise grounding snippets after broad FAQ recall.
        chunk_documents = load_documents(args.chunks_input)
        index_documents(
            "chunk",
            chunk_documents,
            collection=args.chunk_collection,
            persist_dir=args.persist_dir,
            batch_size=args.batch_size,
            reset=not args.no_reset,
        )


if __name__ == "__main__":
    main()
