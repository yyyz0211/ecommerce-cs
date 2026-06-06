"""从 JSONL 加载清洗后的 FAQ 文档和 chunk。"""

from __future__ import annotations

import json
from pathlib import Path

from app.rag.schemas import RAGDocument


def load_documents(path: Path) -> list[RAGDocument]:
    """从 JSONL 文件加载 RAGDocument 行。"""
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
                raise ValueError(f"RAG JSONL 行无效: {path}:{line_no}: {exc}") from exc
    return documents


def load_faq_documents(path: Path) -> list[RAGDocument]:
    """把完整 FAQ 行加载为 FAQ 级别的 RAG 文档。

    清洗后的数据里可能仍包含公告类低价值内容。`kb_candidate` 是爬取结果和知识库
    材料之间的边界，因此在构建索引前就在 loader 中过滤。
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
                raise ValueError(f"FAQ JSONL 行无效: {path}:{line_no}: {exc}") from exc
    return documents
