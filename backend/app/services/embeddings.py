"""Embedding generation service — Gemini text-embedding-004 (768-dim, task-typed).

Generates embeddings for article title + snippet and for search queries; backfill re-embeds
pending/failed articles. The OpenAI client helpers below are retained ONLY for the OpenAI
*generation* provider (llm._generate_openai / summarizer) — the embeddings themselves are Gemini.
"""

import asyncio

import structlog
from openai import AsyncOpenAI

from sqlalchemy import select, update

from app.config import settings
from app.database import async_session
from app.models import Article, EmbeddingStatus

logger = structlog.get_logger()


_cached_user_key: str | None = None
_cached_user_key_ts: float = 0
_USER_KEY_TTL = 300  # 5 minutes cache


async def _get_user_api_key() -> str | None:
    """Check DB for per-user OpenAI key. Cached for 5 minutes."""
    import time

    global _cached_user_key, _cached_user_key_ts

    now = time.time()
    if _cached_user_key is not None and (now - _cached_user_key_ts) < _USER_KEY_TTL:
        return _cached_user_key

    try:
        from sqlalchemy import select as sa_select
        from app.models import UserSetting

        async with async_session() as session:
            result = await session.execute(
                sa_select(UserSetting).where(
                    UserSetting.user_id == 1,
                    UserSetting.openai_api_key_encrypted.isnot(None),
                    UserSetting.openai_key_verified.is_(True),
                )
            )
            setting = result.scalar_one_or_none()

            if setting and setting.openai_api_key_encrypted:
                from app.services.encryption import decrypt_value

                _cached_user_key = decrypt_value(setting.openai_api_key_encrypted)
                _cached_user_key_ts = now
                return _cached_user_key
    except Exception as e:
        logger.debug("user_key_lookup_failed", error=str(e))

    _cached_user_key = None
    _cached_user_key_ts = now
    return None


def _get_client() -> AsyncOpenAI | None:
    """Synchronous client creation — uses env var key only.
    For per-user key support, use _get_client_async()."""
    if not settings.openai_api_key:
        return None
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _get_client_platform() -> AsyncOpenAI | None:
    """Platform (env) key ONLY — never the per-user key. Background graph extraction uses this so it
    bills the platform, not the owner's personal key (which _get_client_async would pick up)."""
    return _get_client()


async def _get_client_async() -> AsyncOpenAI | None:
    """Get OpenAI client: per-user DB key first, env var fallback."""
    user_key = await _get_user_api_key()
    if user_key:
        return AsyncOpenAI(api_key=user_key)
    if settings.openai_api_key:
        return AsyncOpenAI(api_key=settings.openai_api_key)
    return None


async def _resolve_embedding_key() -> str | None:
    """Gemini key for embeddings: the owner's verified per-user key, else the platform env key.
    Reuses the generation-side resolver (lazy import avoids a circular import with llm)."""
    from app.services.llm import _resolve_gemini_key

    return await _resolve_gemini_key()


def _embed_sync(key: str, model: str, content: str, task_type: str) -> list[float]:
    import google.generativeai as genai  # lazy — only on the embedding path

    genai.configure(api_key=key)
    result = genai.embed_content(model=model, content=content, task_type=task_type)
    return result["embedding"]


async def generate_embedding(text: str, *, task_type: str | None = None) -> list[float] | None:
    """Generate a Gemini embedding for a text string. Returns None on failure (never raises).

    task_type defaults to the stored-document type; search passes the query type for asymmetric
    retrieval. Runs the synchronous SDK call in a thread so it never blocks the event loop.
    """
    key = await _resolve_embedding_key()
    if not key:
        logger.warning("embedding_no_gemini_key")
        return None

    try:
        return await asyncio.to_thread(
            _embed_sync,
            key,
            settings.embedding_model,
            text,
            task_type or settings.embedding_task_document,
        )
    except Exception as e:
        logger.error("embedding_generation_failed", error=str(e))
        return None


# Cache of query string -> embedding, so repeated searches for the same query
# reuse one OpenAI call. Bounded to avoid unbounded growth from arbitrary queries.
_query_embedding_cache: dict[str, list[float]] = {}
_QUERY_CACHE_MAX = 512


async def embed_query_cached(text: str) -> list[float] | None:
    """Embed a search query, memoized by the exact query string.

    Uses the same embedding path as generate_embedding so search vectors match
    article vectors. Failures are not cached (so a transient error can retry).
    """
    key = (text or "").strip()
    if not key:
        return None

    cached = _query_embedding_cache.get(key)
    if cached is not None:
        return cached

    embedding = await generate_embedding(key, task_type=settings.embedding_task_query)
    if embedding is not None:
        if len(_query_embedding_cache) >= _QUERY_CACHE_MAX:
            # Simple bound: drop the oldest inserted entry.
            _query_embedding_cache.pop(next(iter(_query_embedding_cache)), None)
        _query_embedding_cache[key] = embedding
    return embedding


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
    if not await _resolve_embedding_key():
        # No Gemini key anywhere → articles ingest but never embed → never cluster → feed/briefing
        # stay empty while /health is green. Log it so this silent dead-stop is observable in prod.
        logger.warning("embedding_backfill_skipped_no_gemini_key")
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
