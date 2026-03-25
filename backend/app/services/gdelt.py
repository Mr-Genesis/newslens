"""GDELT API integration — URL discovery layer.

GDELT provides event metadata with links to source articles.
We use it to discover article URLs, then extract title + snippet via trafilatura.
"""

import re
import structlog
import httpx
import trafilatura

from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Article, Source
from app.services.dedup import is_duplicate

logger = structlog.get_logger()

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


async def fetch_gdelt():
    """Fetch recent articles from GDELT DOC API. Called by APScheduler."""
    async with httpx.AsyncClient(
        headers={"User-Agent": "NewsLens/0.1"},
        follow_redirects=True,
        timeout=60.0,
    ) as client:
        try:
            response = await client.get(
                GDELT_DOC_API,
                params={
                    "query": "sourcecountry:US",
                    "mode": "artlist",
                    "maxrecords": "50",
                    "format": "json",
                    "sort": "datedesc",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("gdelt_fetch_failed", error=str(e))
            return

        try:
            data = response.json()
        except Exception:
            logger.warning("gdelt_json_parse_failed")
            return

        articles = data.get("articles", [])
        if not articles:
            logger.info("gdelt_no_articles")
            return

        new_count = 0
        for item in articles:
            url = item.get("url", "").strip()
            title = item.get("title", "").strip()
            domain = item.get("domain", "").strip()
            seendate = item.get("seendate", "")

            if not url or not title:
                continue

            # Try to extract better snippet via trafilatura
            snippet = await _extract_snippet(client, url)

            # Quality gate: reject garbage snippets
            if snippet and (len(snippet) < settings.min_snippet_length or bool(re.search(r"<[^>]+>", snippet))):
                snippet = None

            # Find or create source for this domain
            source = await _get_or_create_source(domain, url)
            if not source:
                continue

            async with async_session() as session:
                if await is_duplicate(session, source.id, url, title):
                    continue

                pub_date = None
                if seendate:
                    try:
                        pub_date = datetime.strptime(
                            seendate[:14], "%Y%m%d%H%M%S"
                        ).replace(tzinfo=timezone.utc)
                    except (ValueError, IndexError):
                        pass

                article = Article(
                    title=title,
                    snippet=snippet,
                    url=url,
                    source_id=source.id,
                    published_at=pub_date,
                )
                session.add(article)
                await session.commit()
                new_count += 1

        logger.info("gdelt_fetch_complete", new_articles=new_count, checked=len(articles))


async def _extract_snippet(client: httpx.AsyncClient, url: str) -> str | None:
    """Extract article snippet using trafilatura. Returns None on failure."""
    try:
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()
        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            no_fallback=True,
        )
        if extracted:
            return extracted[:300].strip()
    except Exception:
        pass
    return None


async def _get_or_create_source(domain: str, article_url: str) -> Source | None:
    """Find a source by domain or create a new one."""
    base_url = f"https://{domain}"

    async with async_session() as session:
        result = await session.execute(
            select(Source).where(Source.url == base_url).limit(1)
        )
        source = result.scalar_one_or_none()

        if source:
            return source

        # Known paywalled domains
        paywalled_domains = {
            "wsj.com", "ft.com", "bloomberg.com", "nytimes.com",
            "washingtonpost.com", "economist.com", "barrons.com",
            "theathletic.com", "thetimes.co.uk", "telegraph.co.uk",
        }
        is_paywalled = any(d in domain for d in paywalled_domains)

        source = Source(
            name=domain.replace("www.", "").split(".")[0].title(),
            url=base_url,
            source_type="other",
            is_paywalled=is_paywalled,
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source
