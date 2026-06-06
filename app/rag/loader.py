"""Load cleaned FAQ documents and chunks from JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from app.rag.schemas import RAGDocument


def load_documents(path: Path) -> list[RAGDocument]:
    """Load RAGDocument rows from a JSONL file."""
    documents: list[RAGDocument] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                documents.append(RAGDocument.model_validate(payload))
            except Exception as exc:
                raise ValueError(f"Invalid RAG JSONL row at {path}:{line_no}: {exc}") from exc
    return documents


def load_faq_documents(path: Path) -> list[RAGDocument]:
    """Load full FAQ rows as FAQ-level RAG documents.

    Cleaned rows can include low-value announcements. The `kb_candidate` flag is
    the boundary between crawl output and knowledge-base material, so the loader
    filters it here before any index is built.
    """
    documents: list[RAGDocument] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                if payload.get("kb_candidate") is False:
                    continue
                faq_id = str(payload["id"])
                documents.append(
                    RAGDocument(
                        id=f"faq:{faq_id}",
                        faq_id=faq_id,
                        doc_type="faq",
                        chunk_index=0,
                        chunk_count=1,
                        source=str(payload.get("source") or "京东帮助中心"),
                        category=str(payload["category"]),
                        question=str(payload["question"]),
                        text=str(payload.get("text") or payload.get("answer") or ""),
                        url=str(payload["url"]),
                    )
                )
            except Exception as exc:
                raise ValueError(f"Invalid FAQ JSONL row at {path}:{line_no}: {exc}") from exc
    return documents
