"""Wave B2: frameworks endpoint — auto-selected, capped, cached. TDD."""
import pytest

from app.models import (
    Article, ArticleTopic, ClusterArticle, EmbeddingStatus, Source, SourceType,
    StoryCluster, Topic,
)
from app.services.frameworks import FRAMEWORKS

_n = 0


async def _seed_with_topic(db, topic_name):
    global _n
    _n += 1
    src = Source(name="S", url=f"https://f/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    a = Article(title="T", snippet="detail", url=f"https://f/{_n}/a",
                source_id=src.id, embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    cl = StoryCluster(title="C", summary="Sum.")
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    topic = Topic(name=topic_name)
    db.add(topic)
    await db.flush()
    db.add(ArticleTopic(article_id=a.id, topic_id=topic.id, relevance_score=1.0))
    await db.flush()
    return cl


def _patch_llm(monkeypatch, counter):
    import app.services.llm as llm

    async def _gen(prompt, *, system=None, schema=None, model=None, max_tokens=None):
        counter["n"] += 1
        return {"lines": {f["id"]: f"{f['label']} insight grounded in the story." for f in FRAMEWORKS}}

    monkeypatch.setattr(llm, "generate", _gen)


@pytest.mark.asyncio
async def test_frameworks_capped_chips_with_one_liners(aclient, db_session, monkeypatch):
    cl = await _seed_with_topic(db_session, "Geopolitics")
    c = {"n": 0}
    _patch_llm(monkeypatch, c)
    b = (await aclient.get(f"/clusters/{cl.id}/frameworks")).json()
    assert b["story_type"] == "geopolitics"
    assert 1 <= len(b["frameworks"]) <= 4  # capped at 4
    assert all(f["one_liner"] for f in b["frameworks"])
    assert {f["id"] for f in b["frameworks"]} & {"game_theory"}  # game-theory fires on geopolitics
    assert c["n"] == 1


@pytest.mark.asyncio
async def test_frameworks_one_liners_within_word_budget(aclient, db_session, monkeypatch):
    cl = await _seed_with_topic(db_session, "Markets")
    _patch_llm(monkeypatch, {"n": 0})
    b = (await aclient.get(f"/clusters/{cl.id}/frameworks")).json()
    for f in b["frameworks"]:
        assert len(f["one_liner"].split()) <= 20


@pytest.mark.asyncio
async def test_frameworks_cached(aclient, db_session, monkeypatch):
    cl = await _seed_with_topic(db_session, "Markets")
    c = {"n": 0}
    _patch_llm(monkeypatch, c)
    await aclient.get(f"/clusters/{cl.id}/frameworks")
    assert c["n"] == 1
    await aclient.get(f"/clusters/{cl.id}/frameworks")
    assert c["n"] == 1  # served from cache, no second generation


@pytest.mark.asyncio
async def test_frameworks_unavailable_without_key(aclient, db_session):
    cl = await _seed_with_topic(db_session, "Markets")
    b = (await aclient.get(f"/clusters/{cl.id}/frameworks")).json()
    assert b.get("unavailable") is True
