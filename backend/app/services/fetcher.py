"""RSS feed fetcher service with retry and structured logging."""

import html
import json
import re
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
            assigned = False
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
                        assigned = True
            # Only stop here if the embedding pass actually assigned something — an unconditional
            # return stranded every article that cleared no topic at the distance threshold with
            # zero topics forever (they then rendered as "General" everywhere).
            if assigned:
                return

    # Fallback: keyword matching
    text_to_match = (article.title or "").lower()
    if article.snippet:
        text_to_match += " " + article.snippet.lower()

    result = await session.execute(select(Topic))
    topics = result.scalars().all()

    for topic in topics:
        keyword = topic.name.lower()
        # Word-boundary match — plain substring made short topic names poison assignment
        # (e.g. the topic "AI" matched "said", "rain", "email" on every article).
        if re.search(rf"\b{re.escape(keyword)}\b", text_to_match):
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
        from sqlalchemy import exists
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
                # Backfill the Phase-1 tier fields — UNLESS a human has reviewed this row, in which
                # case the seed file must not silently overwrite the curated score every 10 minutes.
                if (existing.credibility_meta or {}).get("reviewed_by") != "admin":
                    if "source_type" in feed:
                        existing.source_type = feed["source_type"]
                    for f in ("author_name", "credibility_score", "credibility_meta",
                              "audience", "is_preprint", "per_fetch_cap"):
                        if f in feed:
                            setattr(existing, f, feed[f])
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
                        author_name=feed.get("author_name"),
                        credibility_score=feed.get("credibility_score"),
                        credibility_meta=feed.get("credibility_meta"),
                        audience=feed.get("audience"),
                        is_preprint=feed.get("is_preprint", False),
                        per_fetch_cap=feed.get("per_fetch_cap"),
                    )
                )
                added += 1
        await session.commit()
    logger.info("sources_ensured", total=len(feeds), added=added)


def _capped_entries(entries, cap: int | None):
    """Trim a feed's entries to a per-source cap (newest-first ⇒ take the first N). None ⇒ all.

    A firehose research feed (arXiv) or a busy wire can otherwise swamp the feed on a single 10-min
    fetch; per_fetch_cap keeps any one source from crowding out the rest.
    """
    if not cap or cap <= 0:
        return entries
    return entries[:cap]


def _best_body(entry) -> str:
    """Return the richest available body text for a feed entry (raw HTML, undecoded).

    Many feeds (Substack, WordPress) ship BOTH a short `summary` and the full-text
    `content:encoded`. Historically we took `summary` and only fell back to `content`, discarding
    the full text exactly when it existed. Take whichever is longer so deep-dive bodies stay rich.
    """
    summary = getattr(entry, "summary", "") or ""
    content = ""
    entry_content = getattr(entry, "content", None)
    if entry_content:
        content = entry_content[0].get("value", "") or ""
    return content if len(content) > len(summary) else summary


_DOUBLE_PREFIX = re.compile(r"^https?://[^/]+/(https?://.+)$", re.IGNORECASE)


def _normalize_link(link: str) -> str:
    """Fix double-prefixed item links (SEBI emits https://www.sebi.gov.in/https://www.sebi.gov.in/…).

    Strips ONLY the exact malformation `scheme://host/scheme://…` — the prefix must be a bare host
    with no real path, so redirect endpoints (/out?next=https://…) and archive links that embed a
    URL deeper in their path are never touched."""
    m = _DOUBLE_PREFIX.match(link)
    return m.group(1) if m else link


def _is_probably_english(text: str) -> bool:
    """Cheap English guard (no LLM), used only for sources flagged credibility_meta.english_guard
    (PIB serves Hindi today). Majority rule over ALPHABETIC chars only, so currency symbols, dashes
    and digits never count against a title, and an English headline quoting one Devanagari name
    survives; a majority-Devanagari title is dropped."""
    if not text:
        return True
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return True  # no letters at all → benefit of the doubt
    ascii_letters = sum(1 for ch in letters if ord(ch) < 128)
    return (ascii_letters / len(letters)) >= 0.5


def _fetch_timeout(source) -> float:
    """Per-source fetch timeout: credibility_meta.fetch_timeout override clamped to [5, 120]s, else
    30s (NITI's server needs ~45s — a hard 30s made it flap). Garbage (negative/inf/nan) → default."""
    import math

    meta = getattr(source, "credibility_meta", None) or {}
    try:
        t = float(meta.get("fetch_timeout") or 30.0)
    except (TypeError, ValueError):
        return 30.0
    if not math.isfinite(t) or t <= 0:
        return 30.0
    return min(120.0, max(5.0, t))


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


async def fetch_single_feed(source: Source, client: httpx.AsyncClient, session=None) -> int:
    """Fetch and parse a single RSS feed. Returns number of new articles.

    Accepts an optional session (tests — the savepoint-wrapped harness session can't share rows
    with a second connection); production opens its own, as before."""
    if not source.rss_url:
        return 0

    try:
        response = await client.get(source.rss_url, timeout=_fetch_timeout(source))
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

    if session is not None:
        return await _ingest_feed_entries(session, source, feed)
    async with async_session() as s:
        return await _ingest_feed_entries(s, source, feed)


async def _ingest_feed_entries(session, source: Source, feed) -> int:
    new_count = 0
    if True:
        for entry in _capped_entries(feed.entries, source.per_fetch_cap):
            # RSS titles/summaries carry HTML entities (&nbsp; &#8377; &amp;) — decode at
            # ingestion so every downstream consumer (cards, summaries, embeddings) sees clean text.
            title = html.unescape(getattr(entry, "title", "").strip())
            link = getattr(entry, "link", "").strip()

            if not title or not link:
                continue

            # English-only guard for flagged sources (PIB currently serves Hindi despite Lang=1;
            # non-English titles would pollute the English embedding space).
            if (source.credibility_meta or {}).get("english_guard") and not _is_probably_english(title):
                continue

            # Resolve relative URLs
            if link.startswith("/"):
                link = source.url.rstrip("/") + link
            # Fix double-prefixed links (SEBI) — also keeps dedup keys sane.
            link = _normalize_link(link)

            # Card snippet from summary/content; keep the FULL text as the body (Wave D1).
            # Take the richer of summary/content — full-text feeds ship both, and the old
            # summary-first branch discarded content:encoded exactly when it was present.
            import re
            raw = _best_body(entry)
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
    if total_new > 0:
        from app.services import events  # #96: signal live clients that new articles landed
        events.publish("feed_refresh", {"new_articles": total_new})
