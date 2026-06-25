"""G1: the global entity backbone.

This module owns reading AND (in later slices) writing the backbone. The two read helpers below are
pure SQL — they surface "who/what is in this story" + "what else touches them", no LLM.

G2 BREADCRUMB: any future LENS that reads graph output must widen its `_source_hash` to include
entity ids + content version + persona/depth (+ user scope at G2), or it will serve stale/cross-tenant
answers. The G1 endpoints are uncached pure-SQL reads, so the trap does not bite yet.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ArticleEntity, ClusterArticle, Entity, StoryCluster


async def cluster_entities(db: AsyncSession, cluster_id: int) -> list[dict]:
    """Cast strip: salient entities across this cluster's articles, deduped by entity (max salience),
    highest-salience first, capped at graph_max_entities_per_cluster."""
    sal = func.max(ArticleEntity.salience).label("salience")
    q = (
        select(Entity.id, Entity.canonical_name, Entity.kind, sal)
        .join(ArticleEntity, ArticleEntity.entity_id == Entity.id)
        .join(ClusterArticle, ClusterArticle.article_id == ArticleEntity.article_id)
        .where(ClusterArticle.cluster_id == cluster_id)
        .group_by(Entity.id, Entity.canonical_name, Entity.kind)
        .order_by(sal.desc())
        .limit(settings.graph_max_entities_per_cluster)
    )
    rows = (await db.execute(q)).all()
    return [
        {"id": r.id, "canonical_name": r.canonical_name, "kind": r.kind, "salience": r.salience}
        for r in rows
    ]


async def entity_clusters(db: AsyncSession, entity_id: int, limit: int = 10) -> list[dict]:
    """'Appears in' rail: other recent clusters whose articles mention this entity, newest first."""
    q = (
        select(StoryCluster.id, StoryCluster.title, StoryCluster.created_at)
        .join(ClusterArticle, ClusterArticle.cluster_id == StoryCluster.id)
        .join(ArticleEntity, ArticleEntity.article_id == ClusterArticle.article_id)
        .where(ArticleEntity.entity_id == entity_id)
        .group_by(StoryCluster.id, StoryCluster.title, StoryCluster.created_at)
        .order_by(StoryCluster.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    return [{"cluster_id": r.id, "title": r.title, "created_at": r.created_at} for r in rows]
