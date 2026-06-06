"""OpenAI-compatible embedding helpers for RAG."""

from __future__ import annotations

from openai import AsyncOpenAI, OpenAI

from app.config import settings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with the configured embedding model."""
    if not texts:
        return []
    client = OpenAI(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_BASE_URL)
    response = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


async def embed_query(query: str) -> list[float]:
    """Embed a single query asynchronously."""
    client = AsyncOpenAI(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_BASE_URL)
    response = await client.embeddings.create(model=settings.EMBEDDING_MODEL, input=query)
    return response.data[0].embedding
