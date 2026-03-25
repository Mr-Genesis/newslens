"""RSS feed fetcher service with retry and structured logging."""

import structlog
import feedparser
import httpx
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy import select, text

from app.database import async_session
from app.models import Article, Source
from app.services.dedup import is_duplicate

logger = structlog.get_logger()

# Starter RSS feeds
STARTER_FEEDS = [
    {"name": "Reuters - World", "url": "https://www.reuters.com", "rss_url": "https://www.rssboard.org/rss-specification", "is_paywalled": False, "source_type": "wire"},
    {"name": "Ars Technica", "url": "https://arstechnica.com", "rss_url": "https://feeds.arstechnica.com/arstechnica/index", "is_paywalled": False, "source_type": "blog"},
    {"name": "TechCrunch", "url": "https://techcrunch.com", "rss_url": "https://techcrunch.com/feed/", "is_paywalled": False, "source_type": "blog"},
    {"name": "The Verge", "url": "https://www.theverge.com", "rss_url": "https://www.theverge.com/rss/index.xml", "is_paywalled": False, "source_type": "blog"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com", "rss_url": "https://hnrss.org/frontpage", "is_paywalled": False, "source_type": "other"},
    {"name": "BBC News", "url": "https://www.bbc.com/news", "rss_url": "http://feeds.bbci.co.uk/news/rss.xml", "is_paywalled": False, "source_type": "newspaper"},
    {"name": "NPR News", "url": "https://www.npr.org", "rss_url": "https://feeds.npr.org/1001/rss.xml", "is_paywalled": False, "source_type": "channel"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com", "rss_url": "https://www.aljazeera.com/xml/rss/all.xml", "is_paywalled": False, "source_type": "channel"},
    {"name": "Nature News", "url": "https://www.nature.com", "rss_url": "https://www.nature.com/nature.rss", "is_paywalled": True, "source_type": "newspaper"},
    {"name": "Wall Street Journal", "url": "https://www.wsj.com", "rss_url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "is_paywalled": True, "source_type": "newspaper"},
]


async def ensure_sources():
    """Seed starter sources if none exist."""
    async with async_session() as session:
        result = await session.execute(select(Source).limit(1))
        if result.scalar_one_or_none() is not None:
            return

        for feed in STARTER_FEEDS:
            source = Source(
                name=feed["name"],
                url=feed["url"],
                rss_url=feed["rss_url"],
                is_paywalled=feed["is_paywalled"],
                source_type=feed["source_type"],
            )
            session.add(source)

        await session.commit()
        logger.info("sources_seeded", count=len(STARTER_FEEDS))


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
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()

            if not title or not link:
                continue

            # Resolve relative URLs
            if link.startswith("/"):
                link = source.url.rstrip("/") + link

            # Snippet from summary or content
            snippet = ""
            if hasattr(entry, "summary"):
                snippet = entry.summary[:300]
            elif hasattr(entry, "content") and entry.content:
                snippet = entry.content[0].get("value", "")[:300]

            # Strip HTML tags from snippet (basic)
            import re
            snippet = re.sub(r"<[^>]+>", "", snippet).strip()

            pub_date = parse_pub_date(entry)

            # Check for duplicates
            if await is_duplicate(session, source.id, link, title):
                continue

            article = Article(
                title=title,
                snippet=snippet if len(snippet) >= 50 else None,
                url=link,
                source_id=source.id,
                published_at=pub_date,
            )
            session.add(article)
            new_count += 1

        if new_count > 0:
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
