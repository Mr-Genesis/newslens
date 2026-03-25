"""Embedding generation service using OpenAI text-embedding-3-small.

Generates embeddings for article title + snippet.
Includes backfill job for articles that failed or were ingested when OpenAI was down.
"""

import structlog
from openai import AsyncOpenAI

from sqlalchemy import select, update

from app.config import settings
from app.database import async_session
from app.models import Article, EmbeddingStatus

logger = structlog.get_logger()


def _get_client() -> AsyncOpenAI | None:
    if not settings.openai_api_key:
        return None
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding for a text string. Returns None on failure."""
    client = _get_client()
    if not client:
        logger.warning("openai_no_api_key")
        return None

    try:
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("embedding_generation_failed", error=str(e))
        return None


async def embed_article(article_id: int):
    """Generate and store embedding for a single article."""
    async with async_session() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id)
        )
        article = result.scalar_one_or_none()
        if not article:
            return

        text = article.title
        if article.snippet:
            text += " " + article.snippet

        embedding = await generate_embedding(text)

        if embedding:
            await session.execute(
                update(Article)
                .where(Article.id == article_id)
                .values(
                    embedding=embedding,
                    embedding_status=EmbeddingStatus.complete,
                )
            )
            await session.commit()
        else:
            await session.execute(
                update(Article)
                .where(Article.id == article_id)
                .values(embedding_status=EmbeddingStatus.failed)
            )
            await session.commit()


async def backfill_embeddings():
    """Backfill embeddings for articles with pending/failed status. Called by APScheduler."""
    client = _get_client()
    if not client:
        return

    async with async_session() as session:
        result = await session.execute(
            select(Article)
            .where(Article.embedding_status.in_([
                EmbeddingStatus.pending,
                EmbeddingStatus.failed,
            ]))
            .order_by(Article.fetched_at.desc())
            .limit(50)
        )
        articles = result.scalars().all()

    if not articles:
        return

    success_count = 0
    for article in articles:
        text = article.title
        if article.snippet:
            text += " " + article.snippet

        embedding = await generate_embedding(text)

        async with async_session() as session:
            if embedding:
                await session.execute(
                    update(Article)
                    .where(Article.id == article.id)
                    .values(
                        embedding=embedding,
                        embedding_status=EmbeddingStatus.complete,
                    )
                )
                success_count += 1
            else:
                await session.execute(
                    update(Article)
                    .where(Article.id == article.id)
                    .values(embedding_status=EmbeddingStatus.failed)
                )
            await session.commit()

    logger.info(
        "embedding_backfill_complete",
        processed=len(articles),
        success=success_count,
    )
