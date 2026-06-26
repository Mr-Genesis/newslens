"""G2 S9: one follow signal personalizes feed + briefing + search (one shared scorer); user-scoped."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Article, ArticleEntity, ClusterArticle, EmbeddingStatus, Entity, Source, SourceType,
    StoryCluster, User, UserEntityRelevance,
)
from app.services import entities as E

_n = 0


async def _ensure_users(db, *ids):
    for uid in ids:
        if (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none() is None:
            db.add(User(id=uid, locale="IN"))
    await db.flush()


async def _src(db):
    global _n
    _n += 1
    s = Source(name="S", url=f"https://all/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _cluster_article(db, src, title, *, published, created):
    global _n
    _n += 1
    a = Article(title=title, url=f"https://all/{_n}/a", source_id=src.id, snippet="snip.",
                published_at=published, embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    cl = StoryCluster(title=title, summary=f"{title} summary.", created_at=created, coherence=0.8)
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return a, cl


async def _follow_entity(db, art, user_id):
    global _n
    _n += 1
    e = Entity(canonical_name="Acme Corp", name_norm=f"acme-{_n}", kind="org")
    db.add(e)
    await db.flush()
    db.add(ArticleEntity(article_id=art.id, entity_id=e.id, salience=0.5))
    db.add(UserEntityRelevance(user_id=user_id, entity_id=e.id, source="follow",
                               engagement_raw=1.0, last_event_at=datetime.now(timezone.utc)))
    await db.flush()


async def _build_world(db, *, follow_user=None):
    """9 clusters. CF ('Acme followed') is feed-NEWEST (published now) but briefing-OLDEST (created
    10h ago), so its climb is attributable to relevance, not recency, on every surface."""
    src = await _src(db)
    now = datetime.now(timezone.utc)
    cf_art, cf_cl = await _cluster_article(db, src, "Acme followed",
                                           published=now, created=now - timedelta(hours=10))
    if follow_user is not None:
        await _follow_entity(db, cf_art, follow_user)
    await _cluster_article(db, src, "Acme plain", published=now, created=now - timedelta(hours=1))
    for i in range(7):
        await _cluster_article(db, src, f"Filler {i}",
                               published=now - timedelta(hours=i + 2), created=now - timedelta(hours=i + 2))
    return cf_art, cf_cl


@pytest.mark.asyncio
async def test_one_follow_lifts_all_surfaces(aclient, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_users(db_session, 1)
    await _build_world(db_session, follow_user=1)

    feed = (await aclient.get("/feed?per_page=50")).json()["articles"]
    assert feed[0]["title"] == "Acme followed"          # recency tie broken by relevance
    brief = (await aclient.get("/briefing")).json()["stories"]
    assert brief[0]["title"] == "Acme followed"          # additive weight lifts the briefing-oldest
    search = (await aclient.get("/search?q=Acme")).json()["results"]
    assert search[0]["title"] == "Acme followed"         # within-tier boost over "Acme plain"


@pytest.mark.asyncio
async def test_user_scoped_isolation(db_session, monkeypatch):
    """user1's follow must not change user2's scores — the LEFT JOIN user_id filter is the control."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_users(db_session, 1, 2)
    _cf_art, cf_cl = await _build_world(db_session, follow_user=1)
    s1 = await E.score_clusters_relevance(db_session, [cf_cl.id], 1)
    s2 = await E.score_clusters_relevance(db_session, [cf_cl.id], 2)
    assert s1.get(cf_cl.id, 0.0) > 0
    assert s2.get(cf_cl.id, 0.0) == 0.0


@pytest.mark.asyncio
async def test_toggle_off_drops_personalization(aclient, db_session, monkeypatch):
    from app.config import settings as s
    await _ensure_users(db_session, 1)
    await _build_world(db_session, follow_user=1)
    monkeypatch.setattr(s, "uer_enabled", True)
    brief_on = (await aclient.get("/briefing")).json()["stories"]
    monkeypatch.setattr(s, "uer_enabled", False)
    brief_off = (await aclient.get("/briefing")).json()["stories"]
    assert brief_on[0]["title"] == "Acme followed"
    assert brief_off[0]["title"] != "Acme followed"  # briefing-oldest → not first once relevance is off
