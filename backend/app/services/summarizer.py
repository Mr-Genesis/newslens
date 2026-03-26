"""AI summary generation service using GPT-4o-mini.

Generates cluster summaries from article titles and snippets.
Hybrid strategy: batch job pre-generates + on-demand fallback.
"""

import structlog
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.config import settings
from app.database import async_session
from app.models import ClusterArticle, StoryCluster, Article, EmbeddingStatus

logger = structlog.get_logger()


async def _get_client():
    """Get OpenAI client — reuses embeddings.py pattern."""
    from app.services.embeddings import _get_client_async
    return await _get_client_async()


async def generate_cluster_summary(
    titles: list[str],
    snippets: list[str],
) -> tuple[str, float]:
    """Generate a summary for a story cluster using GPT-4o-mini.

    Returns (summary_text, coherence_score).
    Coherence is estimated from the number of corroborating sources.
    Falls back to first snippet if OpenAI is unavailable.
    """
    client = await _get_client()

    # Fallback: return first available snippet
    fallback_text = next((s for s in snippets if s), "No summary available.")
    sentences = fallback_text.split(". ")
    fallback_summary = ". ".join(sentences[:2]) + "." if len(sentences) > 1 else fallback_text

    if not client:
        return fallback_summary, 0.70

    # Build prompt from article data
    articles_text = ""
    for i, (title, snippet) in enumerate(zip(titles, snippets), 1):
        articles_text += f"\n{i}. {title}"
        if snippet:
            articles_text += f"\n   {snippet[:300]}"

    try:
        response = await client.chat.completions.create(
            model=settings.summary_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a news analyst. Summarize the following related news articles "
                        "in 2-3 concise sentences. Focus on key facts, implications, and what "
                        "makes this story significant. Be neutral and factual."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Summarize these {len(titles)} related articles:\n{articles_text}",
                },
            ],
            max_tokens=200,
            temperature=0.3,
        )

        summary = response.choices[0].message.content.strip()

        # Estimate coherence from source count (more sources = higher confidence)
        source_count = len(titles)
        if source_count >= 5:
            coherence = 0.95
        elif source_count >= 3:
            coherence = 0.85
        elif source_count >= 2:
            coherence = 0.75
        else:
            coherence = 0.65

        return summary, coherence

    except Exception as e:
        logger.error("summary_generation_failed", error=str(e))
        return fallback_summary, 0.70


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

    summary, coherence = await generate_cluster_summary(titles, snippets)

    # Store on cluster
    async with async_session() as session:
        await session.execute(
            update(StoryCluster)
            .where(StoryCluster.id == cluster_id)
            .values(
                summary=summary,
                coherence=coherence,
                summary_generated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    logger.info(
        "cluster_summary_generated",
        cluster_id=cluster_id,
        coherence=coherence,
        source_count=len(titles),
    )

    return summary, coherence


async def backfill_summaries():
    """Batch job: generate summaries for clusters missing them. Called by APScheduler."""
    async with async_session() as session:
        # Find clusters without summaries or with stale summaries (>4 hours)
        from sqlalchemy import or_

        four_hours_ago = datetime.now(timezone.utc).replace(
            hour=datetime.now(timezone.utc).hour - 4
        )

        result = await session.execute(
            select(StoryCluster.id)
            .where(
                or_(
                    StoryCluster.summary_generated_at.is_(None),
                    StoryCluster.summary.is_(None),
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
