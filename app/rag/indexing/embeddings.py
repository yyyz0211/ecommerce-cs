"""RAG 使用的兼容 OpenAI 协议的向量生成辅助函数。"""

from __future__ import annotations

from openai import AsyncOpenAI, OpenAI

from app.config import settings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """使用当前配置的 embedding 模型批量生成文本向量。"""
    if not texts:
        return []
    client = OpenAI(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_BASE_URL)
    response = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


async def embed_query(query: str) -> list[float]:
    """异步生成单条 query 的向量。"""
    client = AsyncOpenAI(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_BASE_URL)
    response = await client.embeddings.create(model=settings.EMBEDDING_MODEL, input=query)
    return response.data[0].embedding
