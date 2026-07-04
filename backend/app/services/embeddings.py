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


def vector_literal(embedding) -> str:
    """A pgvector text literal — COMMA-separated: "[0.1,0.2,0.3]".

    A pgvector column round-trips as a numpy ndarray, and `str(ndarray)` is SPACE-separated
    ("[0.1 0.2 ...]") and truncates long arrays with "..." — both of which pgvector's parser rejects
    with a syntax error. Every raw `embedding <=> :param` query must build the literal through here
    (works for ndarray AND plain-list embeddings) rather than str(), or the query silently blows up.
    """
    values = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in values) + "]"


class QuotaExceeded(Exception):
    """A Gemini 429 (rate/daily-quota). Raised so the backfill can circuit-break instead of
    re-firing a dead quota every 5 minutes (which torches the ~1,000/day free-tier embedding cap)."""


def _embed_sync(key: str, model: str, content: str, task_type: str, output_dim: int) -> list[float]:
    import google.generativeai as genai  # lazy — only on the embedding path

    genai.configure(api_key=key)
    # output_dimensionality truncates gemini-embedding-001's native 3072 to the pgvector column size.
    result = genai.embed_content(
        model=model, content=content, task_type=task_type, output_dimensionality=output_dim
    )
    return result["embedding"]


def _embed_batch_sync(
    key: str, model: str, texts: list[str], task_type: str, output_dim: int
) -> list[list[float]]:
    """Embed MANY texts in ONE request (BatchEmbedContents). The SDK returns a list-of-embeddings
    when `content` is a list — so N articles cost 1 request, not N, which is what keeps the free-tier
    ~1,000/day embedding cap from being blown on a single backfill pass."""
    import google.generativeai as genai

    genai.configure(api_key=key)
    result = genai.embed_content(
        model=model, content=texts, task_type=task_type, output_dimensionality=output_dim
    )
    return result["embedding"]  # BatchEmbeddingDict → list aligned with `texts` order


# Last embedding failure, surfaced over HTTP by GET /pipeline so the cause of a stalled pipeline
# (quota vs auth vs no-key) is visible at a glance WITHOUT the Render log stream. Process-local: a
# restart clears it, and the next success clears it too (see generate_embedding).
_last_embedding_error: dict | None = None


def _classify_embedding_error(msg: str) -> str:
    """Bucket an embedding error message into an actionable category. `quota` (429 / rate limit —
    the usual free-tier Gemini embedding cap) and `auth` (bad/absent key, permission) are the two
    that change what you do next; everything else is `other`."""
    m = (msg or "").lower()
    if any(k in m for k in ("429", "quota", "resource has been exhausted", "resourceexhausted",
                            "rate limit", "rate_limit")):
        return "quota"
    if any(k in m for k in ("api key", "api_key", "permission", "unauthenticated", "401", "403",
                            "invalid key", "invalid_argument api key")):
        return "auth"
    return "other"


def _record_embedding_error(category: str, message: str) -> None:
    global _last_embedding_error
    from datetime import datetime, timezone

    _last_embedding_error = {
        "when": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "message": (message or "")[:500],
    }


def last_embedding_error() -> dict | None:
    """The most recent embedding failure (or None if the last attempt succeeded / none yet)."""
    return _last_embedding_error


async def generate_embedding(text: str, *, task_type: str | None = None) -> list[float] | None:
    """Generate a Gemini embedding for a text string. Returns None on failure (never raises).

    task_type defaults to the stored-document type; search passes the query type for asymmetric
    retrieval. Runs the synchronous SDK call in a thread so it never blocks the event loop.
    """
    global _last_embedding_error
    key = await _resolve_embedding_key()
    if not key:
        logger.warning("embedding_no_gemini_key")
        _record_embedding_error("no_key", "no Gemini key resolved (per-user key or GEMINI_API_KEY env)")
        return None

    try:
        vec = await asyncio.to_thread(
            _embed_sync,
            key,
            settings.embedding_model,
            text,
            task_type or settings.embedding_task_document,
            settings.embedding_dimensions,
        )
        _last_embedding_error = None  # a success clears the sticky error so /pipeline recovers
        return vec
    except Exception as e:
        msg = str(e)
        category = _classify_embedding_error(msg)
        _record_embedding_error(category, msg)
        logger.error("embedding_generation_failed", category=category, error=msg)
        return None


# After a 429, the backfill parks itself until this epoch so it stops hammering a spent daily quota.
_embedding_backoff_until: float = 0.0


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]] | None:
    """Embed a list of texts in ONE Gemini request. Returns the aligned list of vectors, or None on
    a non-quota failure (no key / transport). Raises QuotaExceeded on a 429 so the caller can back
    off. A success clears the sticky last-error (pipeline recovers)."""
    global _last_embedding_error
    if not texts:
        return []
    key = await _resolve_embedding_key()
    if not key:
        logger.warning("embedding_no_gemini_key")
        _record_embedding_error("no_key", "no Gemini key resolved (per-user key or GEMINI_API_KEY env)")
        return None

    try:
        vecs = await asyncio.to_thread(
            _embed_batch_sync,
            key,
            settings.embedding_model,
            texts,
            settings.embedding_task_document,
            settings.embedding_dimensions,
        )
        _last_embedding_error = None
        return vecs
    except Exception as e:
        msg = str(e)
        category = _classify_embedding_error(msg)
        _record_embedding_error(category, msg)
        logger.error("embedding_batch_failed", category=category, count=len(texts), error=msg)
        if category == "quota":
            raise QuotaExceeded(msg) from e
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


def _article_embed_text(article: Article) -> str:
    text = article.title or ""
    if article.snippet:
        text += " " + article.snippet
    return text


async def backfill_embeddings(session=None):
    """Backfill embeddings for pending/failed articles. Called by APScheduler.

    Sends ONE batched request per `embedding_batch_size` articles (not one per article) to stay
    under the free-tier ~1,000/day cap, and parks itself for a cooldown after a 429 instead of
    re-firing a spent quota every 5 minutes. Accepts an optional session (tests); prod opens its own.
    """
    import time

    global _embedding_backoff_until
    if not await _resolve_embedding_key():
        # No Gemini key anywhere → articles ingest but never embed → never cluster → feed/briefing
        # stay empty while /health is green. Log it so this silent dead-stop is observable in prod.
        logger.warning("embedding_backfill_skipped_no_gemini_key")
        _record_embedding_error("no_key", "no Gemini key resolved (per-user key or GEMINI_API_KEY env)")
        return

    now = time.time()
    if now < _embedding_backoff_until:
        logger.info("embedding_backfill_cooldown", seconds_left=int(_embedding_backoff_until - now))
        return

    if session is not None:
        return await _backfill_once(session)
    async with async_session() as own:
        return await _backfill_once(own)


async def _backfill_once(session):
    import time

    global _embedding_backoff_until
    articles = (
        await session.execute(
            select(Article)
            .where(Article.embedding_status.in_([EmbeddingStatus.pending, EmbeddingStatus.failed]))
            .order_by(Article.fetched_at.desc())
            .limit(settings.embedding_batch_size)
        )
    ).scalars().all()
    if not articles:
        return

    texts = [_article_embed_text(a) for a in articles]
    try:
        vecs = await generate_embeddings_batch(texts)
    except QuotaExceeded:
        _embedding_backoff_until = time.time() + settings.embedding_quota_cooldown_minutes * 60
        logger.warning(
            "embedding_backfill_quota_backoff",
            cooldown_minutes=settings.embedding_quota_cooldown_minutes,
            pending=len(articles),
        )
        return  # leave the articles pending — it wasn't their fault; they retry after the cooldown

    if not vecs:
        # Non-quota whole-batch failure. A batch fails ATOMICALLY, so one poison text (oversized /
        # malformed) would otherwise starve every other article in the batch forever — a new failure
        # mode that batching introduces. Fall back to per-text embedding to ISOLATE the offender:
        # good texts still embed, only the bad one stays failed. If even that embeds nothing
        # (transport / systemic), arm a short backoff so we don't re-fire the same work every 5 min.
        success = 0
        for article, text in zip(articles, texts):
            vec = await generate_embedding(text)
            if vec:
                article.embedding = vec
                article.embedding_status = EmbeddingStatus.complete
                success += 1
            else:
                article.embedding_status = EmbeddingStatus.failed
        await session.commit()
        if success == 0:
            _embedding_backoff_until = time.time() + settings.embedding_error_cooldown_minutes * 60
        logger.warning("embedding_backfill_batch_fallback", processed=len(articles), success=success)
        return

    success = 0
    for article, vec in zip(articles, vecs):
        if vec:
            article.embedding = vec
            article.embedding_status = EmbeddingStatus.complete
            success += 1
        else:
            article.embedding_status = EmbeddingStatus.failed
    await session.commit()
    logger.info("embedding_backfill_complete", processed=len(articles), success=success, api_calls=1)
