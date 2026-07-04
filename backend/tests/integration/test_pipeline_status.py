"""GET /pipeline — at-a-glance pipeline health so a stalled embedding→cluster stage is obvious
without the Render log stream (this is what would have shown '0 embedded, 500 pending' instantly)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Article, ClusterArticle, EmbeddingStatus, Source, SourceType, StoryCluster
from app.services import embeddings


async def _src(db):
    s = Source(name="wire", url="https://w.example", rss_url="https://w.example/rss",
               source_type=SourceType.wire, region="global", category="world")
    db.add(s)
    await db.flush()
    return s


@pytest.mark.asyncio
async def test_pipeline_status_reports_counts(aclient, db_session):
    s = await _src(db_session)
    statuses = [EmbeddingStatus.pending, EmbeddingStatus.pending,
                EmbeddingStatus.complete, EmbeddingStatus.failed]
    for i, st in enumerate(statuses):
        db_session.add(Article(title=f"a{i}", url=f"https://w.example/{i}", source_id=s.id,
                               embedding_status=st, published_at=datetime.now(timezone.utc)))
    await db_session.flush()
    art = (await db_session.execute(select(Article).where(Article.source_id == s.id))).scalars().first()
    c = StoryCluster(title="c", summary="s")
    db_session.add(c)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=c.id, article_id=art.id))
    await db_session.flush()

    r = await aclient.get("/pipeline")
    assert r.status_code == 200
    d = r.json()
    assert d["articles"]["total"] >= 4
    bs = d["articles"]["by_embedding_status"]
    assert bs.get("pending", 0) >= 2
    assert bs.get("complete", 0) >= 1
    assert bs.get("failed", 0) >= 1
    assert d["clusters"]["total"] >= 1
    assert d["clusters"]["articles_clustered"] >= 1


@pytest.mark.asyncio
async def test_pipeline_surfaces_last_embedding_error(aclient, db_session, monkeypatch):
    monkeypatch.setattr(embeddings, "_last_embedding_error",
                        {"category": "quota", "message": "429 exhausted", "when": "2026-07-04T00:00:00Z"})
    d = (await aclient.get("/pipeline")).json()
    assert d["last_embedding_error"]["category"] == "quota"


@pytest.mark.asyncio
async def test_pipeline_clean_when_no_error(aclient, db_session, monkeypatch):
    monkeypatch.setattr(embeddings, "_last_embedding_error", None)
    d = (await aclient.get("/pipeline")).json()
    assert d["last_embedding_error"] is None
