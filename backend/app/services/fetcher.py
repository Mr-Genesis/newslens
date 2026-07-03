"""RSS feed fetcher service with retry and structured logging."""

import html
import json
import structlog
import feedparser
import httpx
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import select, text

from app.database import async_session
from app.models import Article, ArticleTopic, Source, Topic
from app.services.dedup import is_duplicate

logger = structlog.get_logger()


async def assign_topics(session, article: Article):
    """Assign topics to an article using embedding cosine similarity.
    Falls back to keyword matching if article has no embedding or no topic embeddings exist."""
    from app.config import settings

    # Try embedding-based assignment first
    if article.embedding is not None:
        result = await session.execute(
            select(Topic).where(Topic.embedding.isnot(None))
        )
        topics_with_embeddings = result.scalars().all()

        if topics_with_embeddings:
            # Use pgvector cosine distance operator
            for topic in topics_with_embeddings:
                dist_result = await session.execute(
                    text(
                        "SELECT embedding <=> :topic_emb AS distance "
                        "FROM articles WHERE id = :article_id"
                    ),
                    {"topic_emb": str(topic.embedding), "article_id": article.id},
                )
                row = dist_result.first()
                if row and row.distance < settings.new_topic_max_similarity:
                    existing = await session.execute(
                        select(ArticleTopic).where(
                            ArticleTopic.article_id == article.id,
                            ArticleTopic.topic_id == topic.id,
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        session.add(
                            ArticleTopic(
                                article_id=article.id,
                                topic_id=topic.id,
                                relevance_score=1.0 - row.distance,
                            )
                        )
            return

    # Fallback: keyword matching
    text_to_match = (article.title or "").lower()
    if article.snippet:
        text_to_match += " " + article.snippet.lower()

    result = await session.execute(select(Topic))
    topics = result.scalars().all()

    for topic in topics:
        keyword = topic.name.lower()
        if keyword in text_to_match:
            existing = await session.execute(
                select(ArticleTopic).where(
                    ArticleTopic.article_id == article.id,
                    ArticleTopic.topic_id == topic.id,
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(
                    ArticleTopic(article_id=article.id, topic_id=topic.id)
                )


async def backfill_topic_assignments():
    """Batch job: assign topics to articles with embeddings but no topic assignments."""
    async with async_session() as session:
        # Find articles with embeddings but no topic assignments
        from sqlalchemy import exists, and_
        from app.models import EmbeddingStatus

        result = await session.execute(
            select(Article)
            .where(
                Article.embedding_status == EmbeddingStatus.complete,
                ~exists(
                    select(ArticleTopic.id).where(
                        ArticleTopic.article_id == Article.id
                    )
                ),
            )
            .order_by(Article.fetched_at.desc())
            .limit(50)
        )
        articles = result.scalars().all()

    if not articles:
        return

    success = 0
    async with async_session() as session:
        for article in articles:
            # Re-fetch to get embedding in this session
            art_result = await session.execute(
                select(Article).where(Article.id == article.id)
            )
            art = art_result.scalar_one_or_none()
            if art:
                await assign_topics(session, art)
                success += 1
        await session.commit()

    logger.info("topic_assignment_backfill_complete", processed=len(articles), success=success)


_SOURCES_FILE = Path(__file__).resolve().parent.parent / "data" / "sources.json"


def load_feeds() -> list[dict]:
    """Load the configured feed list (global + India) from app/data/sources.json."""
    with open(_SOURCES_FILE, encoding="utf-8") as f:
        return json.load(f)


def google_news_rss_url(
    query: str, *, hl: str = "en-IN", gl: str = "IN", ceid: str = "IN:en"
) -> str:
    """Build a Google News RSS search URL for per-topic ingestion (default: India/English)."""
    return (
        f"https://news.google.com/rss/search?q={quote_plus(query)}"
        f"&hl={hl}&gl={gl}&ceid={ceid}"
    )


async def ensure_sources(session=None):
    """Upsert configured sources: insert new feeds, backfill region/category on existing.

    Keyed on rss_url (fallback url). Safe to run repeatedly — adds feeds to an existing DB
    instead of only seeding when the table is empty. Accepts an optional session (tests).
    """
    if session is not None:
        await _upsert_sources(session, load_feeds())
        return
    async with async_session() as s:
        await _upsert_sources(s, load_feeds())


async def _upsert_sources(session, feeds: list[dict]):
    added = 0
    if True:
        for feed in feeds:
            existing = (
                await session.execute(
                    select(Source).where(Source.rss_url == feed["rss_url"])
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = (
                    await session.execute(
                        select(Source).where(Source.url == feed["url"])
                    )
                ).scalar_one_or_none()
            if existing is not None:
                existing.region = feed.get("region", existing.region)
                existing.category = feed.get("category", existing.category)
                if not existing.rss_url:
                    existing.rss_url = feed["rss_url"]
            else:
                session.add(
                    Source(
                        name=feed["name"],
                        url=feed["url"],
                        rss_url=feed["rss_url"],
                        is_paywalled=feed.get("is_paywalled", False),
                        source_type=feed.get("source_type", "other"),
                        region=feed.get("region", "global"),
                        category=feed.get("category"),
                    )
                )
                added += 1
        await session.commit()
    logger.info("sources_ensured", total=len(feeds), added=added)


def parse_pub_date(entry) -> datetime | None:
    """Parse publication date from a feed entry, handling various formats."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                from time import mktime
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue

    for field in ("published", "updated"):
        raw = getattr(entry, field, None)
        if raw:
            try:
                return parsedate_to_datetime(raw)
            except (ValueError, TypeError):
                continue

    return None


async def fetch_single_feed(source: Source, client: httpx.AsyncClient) -> int:
    """Fetch and parse a single RSS feed. Returns number of new articles."""
    if not source.rss_url:
        return 0

    try:
        response = await client.get(source.rss_url, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("rss_fetch_failed", source=source.name, error=str(e))
        return 0

    content_type = response.headers.get("content-type", "")
    if "html" in content_type and "xml" not in content_type:
        logger.warning("rss_returned_html", source=source.name)
        return 0

    feed = feedparser.parse(response.text)
    if feed.bozo and not feed.entries:
        logger.warning("rss_parse_error", source=source.name, error=str(feed.bozo_exception))
        return 0

    new_count = 0
    async with async_session() as session:
        for entry in feed.entries:
            # RSS titles/summaries carry HTML entities (&nbsp; &#8377; &amp;) — decode at
            # ingestion so every downstream consumer (cards, summaries, embeddings) sees clean text.
            title = html.unescape(getattr(entry, "title", "").strip())
            link = getattr(entry, "link", "").strip()

            if not title or not link:
                continue

            # Resolve relative URLs
            if link.startswith("/"):
                link = source.url.rstrip("/") + link

            # Card snippet from summary/content; keep the FULL text as the body (Wave D1).
            # RSS often ships only a summary, so body may ≈ snippet — graceful degradation.
            import re
            raw = ""
            if hasattr(entry, "summary"):
                raw = entry.summary
            elif hasattr(entry, "content") and entry.content:
                raw = entry.content[0].get("value", "")
            # Strip tags FIRST, then unescape — so an encoded "&lt;script&gt;" never becomes a
            # live tag that the strip would have removed.
            raw = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
            snippet = raw[:300]
            body = raw[:16000] if raw else None

            pub_date = parse_pub_date(entry)

            # Check for duplicates
            if await is_duplicate(session, source.id, link, title):
                continue

            article = Article(
                title=title,
                snippet=snippet if len(snippet) >= 50 else None,
                extracted_text=body,
                url=link,
                source_id=source.id,
                published_at=pub_date,
            )
            session.add(article)
            new_count += 1

        if new_count > 0:
            await session.commit()

            # Assign topics to newly added articles
            result = await session.execute(
                select(Article)
                .where(Article.source_id == source.id)
                .order_by(Article.id.desc())
                .limit(new_count)
            )
            for art in result.scalars().all():
                await assign_topics(session, art)
            await session.commit()

    return new_count


async def fetch_all_rss():
    """Fetch all RSS feeds. Called by APScheduler."""
    await ensure_sources()

    async with async_session() as session:
        result = await session.execute(
            select(Source).where(Source.rss_url.isnot(None))
        )
        sources = result.scalars().all()

    total_new = 0
    async with httpx.AsyncClient(
        headers={"User-Agent": "NewsLens/0.1 (RSS Reader)"},
        follow_redirects=True,
    ) as client:
        for source in sources:
            try:
                count = await fetch_single_feed(source, client)
                total_new += count
                if count > 0:
                    logger.info("rss_fetched", source=source.name, new_articles=count)
            except Exception as e:
                logger.error("rss_fetch_error", source=source.name, error=str(e))

    logger.info("rss_fetch_complete", total_new=total_new, sources_checked=len(sources))
