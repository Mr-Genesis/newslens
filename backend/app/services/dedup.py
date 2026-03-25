"""Article deduplication service.

Dedup rules:
- Same-source: exact URL match OR title similarity > 0.9
- Cross-source: exact URL match only (similar titles from different sources
  are cluster candidates, NOT duplicates)
"""

import structlog
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Article

logger = structlog.get_logger()


async def is_duplicate(
    session: AsyncSession,
    source_id: int,
    url: str,
    title: str,
) -> bool:
    """Check if an article is a duplicate.

    Returns True if:
    - Exact URL match from the same source
    - Title similarity > threshold from the same source
    """
    # 1. Exact URL match (same source)
    result = await session.execute(
        select(Article.id).where(
            Article.url == url,
            Article.source_id == source_id,
        ).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return True

    # 2. Title similarity (same source only — cross-source similar titles are cluster candidates)
    result = await session.execute(
        select(Article.title).where(
            Article.source_id == source_id,
        ).order_by(Article.fetched_at.desc()).limit(100)
    )
    existing_titles = [row[0] for row in result.all()]

    for existing_title in existing_titles:
        similarity = fuzz.ratio(title.lower(), existing_title.lower()) / 100.0
        if similarity > settings.title_similarity_threshold:
            logger.debug(
                "title_dedup_match",
                new_title=title[:60],
                existing_title=existing_title[:60],
                similarity=round(similarity, 3),
            )
            return True

    return False
