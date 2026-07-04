"""Story clustering service using pgvector nearest-neighbor search.

Groups articles about the same event into clusters.
Uses pgvector's <=> cosine distance operator for O(n) lookups instead of
O(n^2) pairwise comparison in Python.
"""

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import (
    Article,
    ArticleTopic,
    ClusterArticle,
    ClusterEdge,
    EmbeddingStatus,
    StoryCluster,
)
from app.services.embeddings import vector_literal

logger = structlog.get_logger()


async def run_clustering():
    """Cluster new articles into story groups. Called by APScheduler."""
    async with async_session() as session:
        # Find articles with embeddings that aren't in any cluster yet
        result = await session.execute(
            select(Article)
            .outerjoin(ClusterArticle)
            .where(
                Article.embedding_status == EmbeddingStatus.complete,
                ClusterArticle.id.is_(None),
            )
            .order_by(Article.fetched_at.desc())
            .limit(100)
        )
        unclustered = result.scalars().all()

    if not unclustered:
        return

    new_clusters = 0
    assigned = 0

    for article in unclustered:
        if article.embedding is None:
            continue

        cluster_id = await _find_nearest_cluster(article)

        async with async_session() as session:
            if cluster_id:
                # Assign to existing cluster
                ca = ClusterArticle(
                    cluster_id=cluster_id,
                    article_id=article.id,
                )
                session.add(ca)
                await session.commit()
                assigned += 1
            else:
                # Create new cluster
                cluster = StoryCluster(title=article.title)
                session.add(cluster)
                await session.flush()

                ca = ClusterArticle(
                    cluster_id=cluster.id,
                    article_id=article.id,
                )
                session.add(ca)
                await session.commit()
                # Wave D2: link the new cluster to prior related clusters (best-effort).
                try:
                    await link_cluster(session, cluster.id)
                except Exception as e:  # noqa: BLE001 — never break clustering on edge-linking
                    logger.warning("cluster_link_failed", cluster_id=cluster.id, error=str(e))
                # Eagerly summarize the brand-new cluster in the background so it's warm before any user
                # opens it — turns the read-path on-demand into a rare cold path (deduped + gated inside).
                from app.services.summarizer import schedule_summary
                schedule_summary(cluster.id)
                new_clusters += 1

    logger.info(
        "clustering_complete",
        unclustered=len(unclustered),
        assigned_to_existing=assigned,
        new_clusters=new_clusters,
    )
    if new_clusters > 0:
        from app.services import events  # #96: signal live clients that new stories formed
        events.publish("new_cluster", {"count": new_clusters})


async def link_cluster(session: AsyncSession, cluster_id: int, max_background: int = 3) -> None:
    """Wave D2: link a cluster to prior clusters sharing a topic — nearest (by id/recency) =
    'successor', next few = 'background'. Idempotent. Powers the 'how we got here' timeline."""
    topic_ids = (
        await session.execute(
            select(ArticleTopic.topic_id)
            .join(ClusterArticle, ClusterArticle.article_id == ArticleTopic.article_id)
            .where(ClusterArticle.cluster_id == cluster_id)
        )
    ).scalars().all()
    if not topic_ids:
        return
    prior = (
        await session.execute(
            select(StoryCluster.id)
            .distinct()
            .join(ClusterArticle, ClusterArticle.cluster_id == StoryCluster.id)
            .join(ArticleTopic, ArticleTopic.article_id == ClusterArticle.article_id)
            .where(ArticleTopic.topic_id.in_(topic_ids), StoryCluster.id < cluster_id)
            .order_by(StoryCluster.id.desc())
            .limit(max_background + 1)
        )
    ).scalars().all()
    for i, prior_id in enumerate(prior):
        kind = "successor" if i == 0 else "background"
        exists = (
            await session.execute(
                select(ClusterEdge.id).where(
                    ClusterEdge.src_cluster_id == cluster_id,
                    ClusterEdge.dst_cluster_id == prior_id,
                    ClusterEdge.kind == kind,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                ClusterEdge(src_cluster_id=cluster_id, dst_cluster_id=prior_id, kind=kind)
            )
    await session.commit()


async def _find_nearest_cluster(article: Article) -> int | None:
    """Find the nearest existing cluster for an article using pgvector.

    Returns cluster_id if a similar article exists within threshold,
    or None if this should start a new cluster.
    """
    async with async_session() as session:
        # Use pgvector cosine distance operator to find similar articles that are already in clusters.
        try:
            result = await session.execute(
                text("""
                    SELECT ca.cluster_id, a.embedding <=> :embedding AS distance
                    FROM articles a
                    JOIN cluster_articles ca ON ca.article_id = a.id
                    WHERE a.embedding IS NOT NULL
                      AND a.embedding <=> :embedding < :threshold
                    ORDER BY distance
                    LIMIT 1
                """),
                {
                    "embedding": vector_literal(article.embedding),
                    "threshold": settings.cluster_similarity_threshold,
                },
            )
            row = result.first()
        except Exception as e:  # noqa: BLE001 — a NN lookup failure must not abort the whole run;
            # fall back to "no match" so the article still starts its own cluster.
            logger.warning("cluster_nn_lookup_failed", article_id=getattr(article, "id", None), error=str(e))
            return None

        if row:
            return row[0]  # cluster_id

    return None
