"""AI summary generation service via the active LLM provider (llm.generate).

Generates cluster summaries from article titles and snippets through the provider abstraction
(OpenAI / Gemini / Anthropic), so summaries follow the configured provider like every other lens.
Hybrid strategy: batch job pre-generates + on-demand fallback.
"""

import asyncio
import structlog
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update

from app.config import settings
from app.database import async_session
from app.models import ClusterArticle, StoryCluster, Article

logger = structlog.get_logger()


def _staleness_cutoff(now: datetime | None = None) -> datetime:
    """Summaries older than this are stale and eligible for refresh.

    Fixes the original ``datetime.now().replace(hour=hour-4)`` bug (ValueError before 4am).
    """
    now = now or datetime.now(timezone.utc)
    return now - timedelta(hours=4)


def snippet_summary(snippets: list[str]) -> str:
    """No-LLM fallback summary: the first non-empty snippet, HTML-unescaped, trimmed to ~2 sentences.

    Returned INSTANTLY by the read paths (/briefing, /clusters/{id}) while the real LLM summary
    generates in the background, and reused as generate_cluster_summary's degradation text. Must never
    be persisted as a cluster's ``summary`` — that would make backfill_summaries treat the cluster as
    done and skip the real generation.
    """
    import html as _html

    text = _html.unescape(next((s for s in snippets if s), "No summary available."))
    sentences = text.split(". ")
    return ". ".join(sentences[:2]) + "." if len(sentences) > 1 else text


async def generate_cluster_summary(
    titles: list[str],
    snippets: list[str],
) -> tuple[str | None, str, float]:
    """Generate an editorial headline + summary for a story cluster via llm.generate.

    Returns (headline | None, summary_text, coherence_score). The headline is a punchy,
    fully fact-supported rewrite (device-QA #2 — raw feed titles like "Government Stock -
    Full Auction Results" don't tell a reader why they should care). None on any failure
    or guard trip → callers keep the existing title. Coherence is estimated from the
    number of corroborating sources.
    """
    # Fallback: first available snippet, trimmed to ~2 sentences — shared with the read-path fallback.
    fallback_summary = snippet_summary(snippets)

    # Coherence heuristic (source-count fallback; the real ratio is computed in lenses.cluster_coherence).
    source_count = len(titles)
    if source_count >= 5:
        coherence = 0.95
    elif source_count >= 3:
        coherence = 0.85
    elif source_count >= 2:
        coherence = 0.75
    else:
        coherence = 0.65

    articles_text = ""
    for i, (title, snippet) in enumerate(zip(titles, snippets), 1):
        articles_text += f"\n{i}. {title}"
        if snippet:
            articles_text += f"\n   {snippet[:300]}"

    from app.services import llm
    try:
        data = await llm.generate(
            f"Rewrite the headline and summarize these {len(titles)} related articles:\n{articles_text}",
            system=(
                "You are a sharp news editor. Respond ONLY as JSON: "
                '{"headline": "...", "summary": "..."}. '
                "headline: one line, UNDER 90 characters, plain language, spark curiosity or "
                "surprise — but every word must be fully supported by the articles; no clickbait "
                "that overpromises, no invented numbers or names. "
                "summary: 2-3 concise, neutral, factual sentences on what happened, why it "
                "matters, and what to watch."
            ),
            schema={"headline": "", "summary": ""},
            max_tokens=260,
        )
    except llm.LLMUnavailable:
        return None, fallback_summary, 0.70
    except Exception as e:  # noqa: BLE001 — never let a summary failure crash the caller
        logger.error("summary_generation_failed", error=str(e))
        return None, fallback_summary, 0.70

    if not isinstance(data, dict):
        return None, fallback_summary, 0.70
    headline = (data.get("headline") or "").strip()
    summary = (data.get("summary") or "").strip()
    # Guard: an over-long/empty headline is worse than the original title.
    if not headline or len(headline) > 90:
        headline = None
    return (headline, summary, coherence) if summary else (headline, fallback_summary, 0.70)


async def summarize_cluster(cluster_id: int) -> tuple[str, float] | None:
    """Generate and store summary for a specific cluster. Returns (summary, coherence) or None."""
    async with async_session() as session:
        result = await session.execute(
            select(StoryCluster)
            .where(StoryCluster.id == cluster_id)
        )
        cluster = result.scalar_one_or_none()
        if not cluster:
            return None

        # Get articles in this cluster
        articles_result = await session.execute(
            select(Article)
            .join(ClusterArticle, ClusterArticle.article_id == Article.id)
            .where(ClusterArticle.cluster_id == cluster_id)
        )
        articles = articles_result.scalars().all()

        if not articles:
            return None

        titles = [a.title for a in articles]
        snippets = [a.snippet or "" for a in articles]

    headline, summary, coherence = await generate_cluster_summary(titles, snippets)

    # Store on cluster; the AI headline replaces the raw first-article title when present.
    async with async_session() as session:
        await session.execute(
            update(StoryCluster)
            .where(StoryCluster.id == cluster_id)
            .values(
                summary=summary,
                coherence=coherence,
                summary_generated_at=datetime.now(timezone.utc),
                **({"title": headline} if headline else {}),
            )
        )
        await session.commit()

    logger.info(
        "cluster_summary_generated",
        cluster_id=cluster_id,
        coherence=coherence,
        source_count=len(titles),
        headline=bool(headline),
    )

    return summary, coherence


# Clusters currently being summarized in the background — dedupes a burst of read requests (or eager
# creation) so only ONE task per cluster is in flight at a time.
_scheduled: set[int] = set()


def schedule_summary(cluster_id: int) -> "asyncio.Task | None":
    """Fire-and-forget background summary generation for a cluster.

    The read paths call this instead of awaiting summarize_cluster, so /briefing and /clusters/{id}
    return instantly (with a snippet fallback) and the real summary is warm on the next view. Deduped
    per cluster and gated by ``settings.eager_summaries_enabled``. Returns the Task, or None when it was
    deduped / gated off / there is no running event loop.
    """
    if not settings.eager_summaries_enabled:
        return None
    if cluster_id in _scheduled:
        return None
    _scheduled.add(cluster_id)

    async def _run() -> None:
        try:
            await summarize_cluster(cluster_id)
        except Exception as e:  # noqa: BLE001 — best-effort; backfill_summaries retries misses
            logger.warning("scheduled_summary_failed", cluster_id=cluster_id, error=str(e))
        finally:
            _scheduled.discard(cluster_id)

    try:
        return asyncio.create_task(_run())
    except RuntimeError:
        # No running loop (e.g. invoked from a sync context) — undo the guard so a later call retries.
        _scheduled.discard(cluster_id)
        return None


async def backfill_summaries():
    """Batch job: generate summaries for clusters missing them. Called by APScheduler."""
    async with async_session() as session:
        # Find clusters without summaries or with stale summaries (>4 hours)
        from sqlalchemy import or_

        cutoff = _staleness_cutoff()

        result = await session.execute(
            select(StoryCluster.id)
            .where(
                or_(
                    StoryCluster.summary_generated_at.is_(None),
                    StoryCluster.summary.is_(None),
                    StoryCluster.summary_generated_at < cutoff,
                )
            )
            .order_by(StoryCluster.created_at.desc())
            .limit(settings.summary_batch_size)
        )
        cluster_ids = [row[0] for row in result.all()]

    if not cluster_ids:
        return

    success = 0
    for cid in cluster_ids:
        result = await summarize_cluster(cid)
        if result:
            success += 1

    logger.info(
        "summary_backfill_complete",
        processed=len(cluster_ids),
        success=success,
    )
