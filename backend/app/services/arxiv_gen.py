"""Phase 3 · #87 — generate arXiv category feeds from user interests.

Phase 1 seeded four arXiv feeds (cs.AI, cs.LG, econ.GN, q-fin). This maps the interests users
actually hold (their subscribed topics) to further arXiv categories and ensures those research
sources exist — so a computer-vision or robotics enthusiast gets that category's preprints. Source
creation reuses fetcher._upsert_sources, so it's idempotent and honors the admin-lock.
"""
import structlog
from sqlalchemy import select

from app.database import async_session
from app.models import Source, Topic, UserPreference

logger = structlog.get_logger()

# interest keyword (substring of a topic name) → (arXiv category, audience tags). Categories already
# seeded in Phase 1 (cs.AI, cs.LG) are intentionally omittable here; _upsert_sources dedups anyway.
_INTEREST_ARXIV: dict[str, tuple[str, list[str]]] = {
    "computer vision": ("cs.CV", ["ai", "technology"]),
    "vision": ("cs.CV", ["ai", "technology"]),
    "language": ("cs.CL", ["ai"]),
    "nlp": ("cs.CL", ["ai"]),
    "robotic": ("cs.RO", ["engineering", "ai"]),
    "security": ("cs.CR", ["software", "technology"]),
    "cryptograph": ("cs.CR", ["software", "technology"]),
    "quantum": ("quant-ph", ["science"]),
    "biolog": ("q-bio", ["science", "medicine"]),
    "statistic": ("stat.ML", ["ai", "science"]),
    "distributed": ("cs.DC", ["software", "technology"]),
    "systems": ("cs.DC", ["software", "technology"]),
    "graphics": ("cs.GR", ["technology"]),
    "database": ("cs.DB", ["software"]),
}


def arxiv_categories_for_interests(interests) -> dict[str, list[str]]:
    """Map free-text interests to arXiv categories → audience tags (deduped by category)."""
    out: dict[str, list[str]] = {}
    for interest in interests or []:
        if not interest:
            continue
        text = f" {interest.lower()} "
        for kw, (cat, tags) in _INTEREST_ARXIV.items():
            if kw in text:
                out[cat] = tags
    return out


def arxiv_source_spec(cat: str, tags: list[str]) -> dict:
    """A sources.json-shaped spec for an arXiv category feed."""
    return {
        "name": f"arXiv {cat}",
        "url": f"https://arxiv.org/list/{cat}/recent",
        "rss_url": f"https://rss.arxiv.org/rss/{cat}",
        "is_paywalled": False,
        "source_type": "research",
        "region": "global",
        "category": "research",
        "credibility_score": 80,
        "audience": tags,
        "is_preprint": True,
        "per_fetch_cap": 25,
    }


async def generate_arxiv_sources(session=None, interests=None) -> int:
    """Ensure arXiv sources for the given interests (or all users' subscribed topics). Returns the
    number of newly-created sources. Idempotent — an existing (or admin-locked) source is untouched."""
    if session is not None:
        return await _generate(session, interests)
    async with async_session() as s:
        return await _generate(s, interests)


async def _generate(session, interests) -> int:
    from app.services import fetcher  # local import avoids any import cycle at module load

    if interests is None:
        rows = await session.execute(
            select(Topic.name).join(UserPreference, UserPreference.topic_id == Topic.id).distinct()
        )
        interests = [r[0] for r in rows.all()]

    cats = arxiv_categories_for_interests(interests)
    if not cats:
        return 0
    specs = [arxiv_source_spec(cat, tags) for cat, tags in sorted(cats.items())]

    rss_urls = [s["rss_url"] for s in specs]
    existing = set(
        (await session.execute(select(Source.rss_url).where(Source.rss_url.in_(rss_urls)))).scalars().all()
    )
    await fetcher._upsert_sources(session, specs)
    created = sum(1 for u in rss_urls if u not in existing)
    logger.info("arxiv_sources_generated", categories=len(specs), created=created)
    return created
