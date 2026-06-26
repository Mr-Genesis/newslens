"""G2 S7: /briefing additive entity-relevance blend into story_weights (exploit/explore untouched)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Article, ArticleEntity, ClusterArticle, EmbeddingStatus, Entity, Source, SourceType,
    StoryCluster, User, UserEntityRelevance,
)

_n = 0


async def _ensure_user1(db):
    if (await db.execute(select(User).where(User.id == 1))).scalar_one_or_none() is None:
        db.add(User(id=1, locale="IN"))
        await db.flush()


async def _src(db):
    global _n
    _n += 1
    s = Source(name="S", url=f"https://brief/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _bcluster(db, src, title, created_at, followed=False):
    global _n
    _n += 1
    cl = StoryCluster(title=title, summary=f"{title} summary.", created_at=created_at, coherence=0.8)
    db.add(cl)
    await db.flush()
    a = Article(title=title, url=f"https://brief/{_n}/a", source_id=src.id, snippet="snip.",
                embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    if followed:
        _n += 1
        e = Entity(canonical_name="E", name_norm=f"e-{_n}", kind="org")
        db.add(e)
        await db.flush()
        db.add(ArticleEntity(article_id=a.id, entity_id=e.id, salience=0.5))
        db.add(UserEntityRelevance(user_id=1, entity_id=e.id, source="follow",
                                   engagement_raw=1.0, last_event_at=datetime.now(timezone.utc)))
    await db.flush()
    return cl


async def _seed_nine(db, src, now, followed_relevant: bool):
    """The 'Relevant' cluster is the OLDEST (last by recency); 8 newer 'Plain' clusters, no topic prefs."""
    await _bcluster(db, src, "Relevant", now - timedelta(hours=20), followed=followed_relevant)
    for i in range(8):
        await _bcluster(db, src, f"Plain {i}", now - timedelta(hours=i + 1))


@pytest.mark.asyncio
async def test_briefing_on_relevance_lifts_into_exploit(aclient, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    await _seed_nine(db_session, src, datetime.now(timezone.utc), followed_relevant=True)
    titles = [st["title"] for st in (await aclient.get("/briefing")).json()["stories"]]
    assert titles[0] == "Relevant"  # relevance (additive, zero topic pref) lifted the oldest to the top


@pytest.mark.asyncio
async def test_briefing_off_relevance_has_no_effect(aclient, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", False)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    await _seed_nine(db_session, src, datetime.now(timezone.utc), followed_relevant=True)
    titles = [st["title"] for st in (await aclient.get("/briefing")).json()["stories"]]
    assert titles[0] != "Relevant"  # off → oldest cluster with no topic pref stays at the bottom


@pytest.mark.asyncio
async def test_briefing_zero_uer_identical_to_off(aclient, db_session, monkeypatch):
    from app.config import settings as s
    src = await _src(db_session)
    now = datetime.now(timezone.utc)
    await _ensure_user1(db_session)
    await _seed_nine(db_session, src, now, followed_relevant=False)  # no follows anywhere

    monkeypatch.setattr(s, "uer_enabled", True)
    on = [st["title"] for st in (await aclient.get("/briefing")).json()["stories"]]
    monkeypatch.setattr(s, "uer_enabled", False)
    off = [st["title"] for st in (await aclient.get("/briefing")).json()["stories"]]
    assert on == off  # no relevance signal → +0 → identical ordering
