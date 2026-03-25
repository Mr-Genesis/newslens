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
from app.models import Article, ClusterArticle, EmbeddingStatus, StoryCluster

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
                new_clusters += 1

    logger.info(
        "clustering_complete",
        unclustered=len(unclustered),
        assigned_to_existing=assigned,
        new_clusters=new_clusters,
    )


async def _find_nearest_cluster(article: Article) -> int | None:
    """Find the nearest existing cluster for an article using pgvector.

    Returns cluster_id if a similar article exists within threshold,
    or None if this should start a new cluster.
    """
    async with async_session() as session:
        # Use pgvector cosine distance operator to find similar articles
        # that are already in clusters
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
                "embedding": str(article.embedding),
                "threshold": settings.cluster_similarity_threshold,
            },
        )
        row = result.first()

        if row:
            return row[0]  # cluster_id

    return None
