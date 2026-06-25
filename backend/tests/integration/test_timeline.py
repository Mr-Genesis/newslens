"""Wave D2: "how we got here" timeline lens. TDD."""
from datetime import datetime, timezone

import pytest

from app.models import (
    Article, ClusterArticle, ClusterEdge, EmbeddingStatus, Source, SourceType, StoryCluster,
)

_n = 0


async def _seed(db, title="Now"):
    global _n
    _n += 1
    src = Source(name="S", url=f"https://tl/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    a = Article(title="Art", snippet="s", url=f"https://tl/{_n}/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete,
                published_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    db.add(a)
    await db.flush()
    cl = StoryCluster(title=title)
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return cl


def _patch(monkeypatch, counter):
    import app.services.llm as llm

    async def _gen(prompt, *, system=None, schema=None, model=None, max_tokens=None):
        counter["n"] += 1
        return {"how_we_got_here": "It started months ago.",
                "timeline": [{"when": "June", "what": "X happened"}]}

    monkeypatch.setattr(llm, "generate", _gen)


@pytest.mark.asyncio
async def test_timeline_returns_how_we_got_here(aclient, db_session, monkeypatch):
    cl = await _seed(db_session)
    c = {"n": 0}
    _patch(monkeypatch, c)
    b = (await aclient.get(f"/clusters/{cl.id}/timeline")).json()
    assert b["how_we_got_here"]
    assert isinstance(b["timeline"], list)
    assert c["n"] == 1


@pytest.mark.asyncio
async def test_timeline_cached(aclient, db_session, monkeypatch):
    cl = await _seed(db_session)
    c = {"n": 0}
    _patch(monkeypatch, c)
    await aclient.get(f"/clusters/{cl.id}/timeline")
    assert c["n"] == 1
    await aclient.get(f"/clusters/{cl.id}/timeline")
    assert c["n"] == 1


@pytest.mark.asyncio
async def test_timeline_includes_prior_related_clusters(aclient, db_session, monkeypatch):
    cl = await _seed(db_session, "Now")
    prior = await _seed(db_session, "Earlier event")
    db_session.add(ClusterEdge(src_cluster_id=cl.id, dst_cluster_id=prior.id, kind="background"))
    await db_session.flush()
    sink = {}
    import app.services.llm as llm

    async def _gen(prompt, *, system=None, schema=None, model=None, max_tokens=None):
        sink["prompt"] = prompt
        return {"how_we_got_here": "x", "timeline": []}

    monkeypatch.setattr(llm, "generate", _gen)
    await aclient.get(f"/clusters/{cl.id}/timeline")
    assert "Earlier event" in sink["prompt"]  # prior cluster surfaced into the timeline
