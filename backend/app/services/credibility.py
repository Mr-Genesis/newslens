"""Phase 3 · #90 — monthly LLM credibility review (propose-only).

Re-assesses gated (expert/research) sources whose credibility hasn't been reviewed in >90 days and
writes a PROPOSAL — never a live change. It sets `credibility_meta.proposed_score` (+ `last_reviewed`
+ `reviewed_by="llm-proposed"`) and leaves the live `credibility_score` untouched; a human applies it
via PUT /admin/sources/{id}/credibility (#85). An admin-locked row keeps its lock and live score.

The score is an *editorial* estimate from model knowledge, never an objective ranking of a person.
"""
from datetime import datetime, timezone

import structlog

from app.config import settings
from app.database import async_session
from app.models import Source, SourceType
from app.services import llm

logger = structlog.get_logger()

_RUBRIC = (
    "Rate the editorial credibility of this source's author on a 0-100 scale using: affiliation/"
    "institutional role (30), education/credentials (20), track record/mainstream citation (25), "
    "audience scale (15), original analysis vs aggregation (10). 90+ canonical authority, 75-89 "
    "established expert, 60-74 credible practitioner, <55 discover-only."
)

_SCORE_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}, "rationale": {"type": "string"}},
    "required": ["score"],
}


async def _propose_score(source: Source) -> int | None:
    """Ask the platform LLM to re-estimate a 0-100 credibility score. Returns None on unavailability."""
    prompt = (
        f"{_RUBRIC}\n\nSource: {source.name}\nAuthor: {source.author_name or 'unknown'}\n"
        f"Current score: {source.credibility_score}\nReturn JSON {{\"score\": <0-100>, \"rationale\": <str>}}."
    )
    try:
        result = await llm.generate(prompt, schema=_SCORE_SCHEMA, force_platform_key=True)
        score = result.get("score") if isinstance(result, dict) else None
        if score is None:
            return None
        # int() is INSIDE the try: an LLM that returns {"score": "high"} / [85] / "85%" must not
        # abort the whole monthly run and discard the proposals already written for earlier rows.
        return max(0, min(100, int(score)))
    except llm.LLMUnavailable:
        return None
    except Exception as e:  # noqa: BLE001 — a bad LLM response must not abort the whole run
        logger.warning("credibility_propose_failed", source=source.name, error=str(e))
        return None


def _is_stale(meta: dict, cutoff: datetime) -> bool:
    last = (meta or {}).get("last_reviewed")
    if not last:
        return True  # never reviewed
    try:
        dt = datetime.fromisoformat(last)
    except (TypeError, ValueError):
        return True  # unparseable → treat as stale, re-stamp it
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # tolerate a naive/date-only stored value vs aware cutoff
    return dt <= cutoff


async def review_credibility(session=None, *, now=None) -> int:
    """Propose fresh scores for stale gated sources. Returns the number of proposals written.

    `now` is injectable for deterministic tests. Accepts an optional session (tests); otherwise
    opens its own (the scheduler path).
    """
    if session is not None:
        return await _review(session, now=now)
    async with async_session() as s:
        return await _review(s, now=now)


async def _review(session, *, now=None) -> int:
    from datetime import timedelta

    from sqlalchemy import select

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.credibility_review_stale_days)

    sources = (
        await session.execute(
            select(Source).where(Source.source_type.in_([SourceType.expert, SourceType.research]))
        )
    ).scalars().all()

    proposed = 0
    for source in sources:
        meta = dict(source.credibility_meta or {})
        if not _is_stale(meta, cutoff):
            continue
        score = await _propose_score(source)
        if score is None:
            continue  # LLM unavailable / bad response → skip this row, no-op
        meta["proposed_score"] = score
        meta["last_reviewed"] = now.isoformat()
        # Never downgrade an admin lock — a proposal is recorded, but the human decision stands.
        if meta.get("reviewed_by") != "admin":
            meta["reviewed_by"] = "llm-proposed"
        source.credibility_meta = meta
        # The live `credibility_score` is DELIBERATELY untouched — this job proposes, never decides.
        proposed += 1

    await session.commit()
    logger.info("credibility_review_complete", candidates=len(sources), proposed=proposed)
    return proposed
