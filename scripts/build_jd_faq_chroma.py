"""从清洗后的京东 FAQ 数据构建 Chroma 索引。

前置条件：
    1. 已生成 data/jd_faq_clean.jsonl 和 data/jd_faq_chunks.jsonl
    2. 已安装 chromadb
    3. 已配置 EMBEDDING_API_KEY / OPENAI_API_KEY

示例：
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
from app.rag.indexing.embeddings import embed_texts
from app.rag.indexing.loader import load_documents, load_faq_documents
from app.rag.indexing.vector_store import add_documents, reset_collection

DEFAULT_CLEAN_INPUT = Path("data/jd_faq_clean.jsonl")
DEFAULT_CHUNKS_INPUT = Path("data/jd_faq_chunks.jsonl")


def batched(items, batch_size: int):
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建京东 FAQ Chroma 索引。")
    parser.add_argument("--clean-input", type=Path, default=DEFAULT_CLEAN_INPUT)
    parser.add_argument("--chunks-input", "--input", dest="chunks_input", type=Path, default=DEFAULT_CHUNKS_INPUT)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--persist-dir", default=settings.CHROMA_PERSIST_DIR)
    parser.add_argument("--doc-collection", default=settings.CHROMA_DOC_COLLECTION)
    parser.add_argument("--chunk-collection", "--collection", dest="chunk_collection", default=settings.CHROMA_CHUNK_COLLECTION)
    parser.add_argument("--only", choices=("all", "docs", "chunks"), default="all")
    parser.add_argument("--no-reset", action="store_true", help="追加到现有 collection，而不是重建。")
    return parser.parse_args()


def index_documents(label: str, documents, *, collection: str, persist_dir: str, batch_size: int, reset: bool) -> None:
    if not documents:
        raise SystemExit(f"未加载到 {label} 文档")

    if reset:
        reset_collection(collection, persist_dir)

    total = len(documents)
    indexed = 0
    for batch in batched(documents, batch_size):
        embeddings = embed_texts([doc.text for doc in batch])
        add_documents(batch, embeddings, collection_name=collection, persist_dir=persist_dir)
        indexed += len(batch)
        print(f"已索引 {label} {indexed}/{total}")

    print(f"完成。label={label} collection={collection} persist_dir={persist_dir} documents={total}")


def main() -> None:
    args = parse_args()

    if args.only in ("all", "docs"):
        # FAQ 级别文档用于提升宽泛政策问题的召回效果。
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
        # Chunk 级别文档用于在宽泛召回后提供更精确的证据片段。
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
