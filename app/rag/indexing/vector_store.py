"""Chroma 向量库封装。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.config import settings
from app.rag.schemas import RAGDocument, RAGMatch


def get_chroma_client(persist_dir: Optional[str] = None):
    """返回持久化 Chroma client。

    Chroma 使用懒加载，避免依赖尚未安装或向量索引尚未构建时影响应用启动。
    """
    import chromadb

    path = persist_dir or settings.CHROMA_PERSIST_DIR
    Path(path).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=path)


def get_collection(collection_name: Optional[str] = None, persist_dir: Optional[str] = None):
    client = get_chroma_client(persist_dir)
    return client.get_or_create_collection(
        name=collection_name or settings.CHROMA_CHUNK_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(collection_name: Optional[str] = None, persist_dir: Optional[str] = None):
    import chromadb

    path = persist_dir or settings.CHROMA_PERSIST_DIR
    Path(path).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=path)
    name = collection_name or settings.CHROMA_CHUNK_COLLECTION
    try:
        client.delete_collection(name)
    except Exception:
        pass
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def add_documents(
    documents: list[RAGDocument],
    embeddings: list[list[float]],
    *,
    collection_name: Optional[str] = None,
    persist_dir: Optional[str] = None,
) -> None:
    if len(documents) != len(embeddings):
        raise ValueError("文档和向量数量不一致")
    if not documents:
        return

    collection = get_collection(collection_name, persist_dir)
    collection.add(
        ids=[doc.id for doc in documents],
        documents=[doc.text for doc in documents],
        embeddings=embeddings,
        metadatas=[
            {
                "faq_id": doc.faq_id,
                "doc_type": doc.doc_type,
                "chunk_index": doc.chunk_index,
                "chunk_count": doc.chunk_count,
                "source": doc.source,
                "category": doc.category,
                "question": doc.question,
                "url": doc.url,
                "section_title": doc.section_title or "",
            }
            for doc in documents
        ],
    )


def query_documents(
    query_embedding: list[float],
    *,
    top_k: int = 5,
    category: Optional[str] = None,
    collection_name: Optional[str] = None,
    persist_dir: Optional[str] = None,
) -> list[RAGMatch]:
    collection = get_collection(collection_name, persist_dir)
    where = {"category": category} if category else None
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    matches: list[RAGMatch] = []
    for doc_id, text, metadata, distance in zip(ids, docs, metadatas, distances):
        # Chroma 的余弦距离越低越好；这里换算出的 score 只用于展示/过滤，
        # 不是校准后的概率。
        score = None if distance is None else max(0.0, 1.0 - float(distance))
        matches.append(
            RAGMatch(
                id=doc_id,
                faq_id=str(metadata.get("faq_id", "")),
                doc_type=str(metadata.get("doc_type", "chunk")),
                chunk_index=int(metadata.get("chunk_index", 0)),
                chunk_count=int(metadata.get("chunk_count", 1)),
                category=str(metadata.get("category", "")),
                question=str(metadata.get("question", "")),
                text=text,
                url=str(metadata.get("url", "")),
                source=str(metadata.get("source", "京东帮助中心")),
                section_title=str(metadata.get("section_title") or "") or None,
                distance=float(distance) if distance is not None else None,
                score=score,
                retrieval_source=None,
            )
        )
    return matches
