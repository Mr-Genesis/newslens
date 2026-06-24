"""Wave D2: link_cluster — topic+recency edges between clusters. TDD."""
import pytest
from sqlalchemy import select

from app.models import (
    Article, ArticleTopic, ClusterArticle, ClusterEdge, EmbeddingStatus, Source,
    SourceType, StoryCluster, Topic,
)
from app.services.clustering import link_cluster

_n = 0


async def _cluster_with_topic(db, topic, title="C"):
    global _n
    _n += 1
    src = Source(name="S", url=f"https://ce/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    a = Article(title=title, snippet="s", url=f"https://ce/{_n}/a",
                source_id=src.id, embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    cl = StoryCluster(title=title)
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    db.add(ArticleTopic(article_id=a.id, topic_id=topic.id, relevance_score=1.0))
    await db.flush()
    return cl


@pytest.mark.asyncio
async def test_link_cluster_makes_successor_to_prior_same_topic(aclient, db_session):
    t = Topic(name="Energy")
    db_session.add(t)
    await db_session.flush()
    older = await _cluster_with_topic(db_session, t, "Older")
    newer = await _cluster_with_topic(db_session, t, "Newer")
    await link_cluster(db_session, newer.id)
    edges = (await db_session.execute(
        select(ClusterEdge).where(ClusterEdge.src_cluster_id == newer.id))).scalars().all()
    assert any(e.dst_cluster_id == older.id and e.kind == "successor" for e in edges)


@pytest.mark.asyncio
async def test_link_cluster_is_idempotent(aclient, db_session):
    t = Topic(name="Trade")
    db_session.add(t)
    await db_session.flush()
    await _cluster_with_topic(db_session, t, "Older")
    newer = await _cluster_with_topic(db_session, t, "Newer")
    await link_cluster(db_session, newer.id)
    await link_cluster(db_session, newer.id)
    edges = (await db_session.execute(
        select(ClusterEdge).where(ClusterEdge.src_cluster_id == newer.id))).scalars().all()
    assert len(edges) == 1  # one prior → one successor edge, not duplicated


@pytest.mark.asyncio
async def test_link_cluster_no_topic_no_edges(aclient, db_session):
    src = Source(name="S", url="https://ce/x", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    a = Article(title="T", url="https://ce/x/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete)
    db_session.add(a)
    await db_session.flush()
    cl = StoryCluster(title="T")
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db_session.flush()
    await link_cluster(db_session, cl.id)
    edges = (await db_session.execute(
        select(ClusterEdge).where(ClusterEdge.src_cluster_id == cl.id))).scalars().all()
    assert edges == []
