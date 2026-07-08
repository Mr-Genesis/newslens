"""G2 S6: /feed bounded-pool rerank — byte-identical when off, recency+relevance blend when on."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select

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
    s = Source(name="S", url=f"https://feed/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _article(db, src, when, title):
    global _n
    _n += 1
    a = Article(title=title, url=f"https://feed/{_n}/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete, published_at=when)
    db.add(a)
    await db.flush()
    return a


async def _follow_articles_entity(db, *arts, user_id=1):
    """Put the articles in one cluster and make the current user follow its (one) entity."""
    global _n
    cl = StoryCluster(title="C")
    db.add(cl)
    await db.flush()
    for a in arts:
        db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    _n += 1
    e = Entity(canonical_name="Followed", name_norm=f"followed-{_n}", kind="org")
    db.add(e)
    await db.flush()
    for a in arts:
        db.add(ArticleEntity(article_id=a.id, entity_id=e.id, salience=0.5))
    db.add(UserEntityRelevance(user_id=user_id, entity_id=e.id, source="follow",
                               engagement_raw=1.0, last_event_at=datetime.now(timezone.utc)))
    await db.flush()
    return cl


@pytest.mark.asyncio
async def test_feed_off_is_recency_and_true_total(aclient, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", False)
    src = await _src(db_session)
    now = datetime.now(timezone.utc)
    await _article(db_session, src, now - timedelta(days=2), "Old")
    await _article(db_session, src, now, "New")
    await db_session.flush()
    body = (await aclient.get("/feed?per_page=50")).json()
    titles = [it["title"] for it in body["articles"]]
    assert titles.index("New") < titles.index("Old")  # pure recency
    assert body["total"] == 2  # true corpus count when off


@pytest.mark.asyncio
async def test_feed_on_bubbles_followed_entity(aclient, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    now = datetime.now(timezone.utc)
    await _article(db_session, src, now, "Plain")  # newest, unrelated
    foll = await _article(db_session, src, now, "Followed story")  # same time, followed
    await _follow_articles_entity(db_session, foll)
    body = (await aclient.get("/feed?per_page=50")).json()
    titles = [it["title"] for it in body["articles"]]
    assert titles.index("Followed story") < titles.index("Plain")  # relevance breaks the recency tie


@pytest.mark.asyncio
async def test_feed_on_recency_dominates_by_default(aclient, db_session, monkeypatch):
    """Default blend ratio 0.3 keeps recency primary: a much-newer unrelated story beats an old follow."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    now = datetime.now(timezone.utc)
    await _article(db_session, src, now, "Newest")
    old = await _article(db_session, src, now - timedelta(days=10), "Old followed")
    await _follow_articles_entity(db_session, old)
    body = (await aclient.get("/feed?per_page=50")).json()
    titles = [it["title"] for it in body["articles"]]
    assert titles.index("Newest") < titles.index("Old followed")


@pytest.mark.asyncio
async def test_feed_on_high_affinity_crosses_to_page_1(aclient, db_session, monkeypatch):
    """With relevance weighted high, a followed-but-old story crosses from page 2 into page 1."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    monkeypatch.setattr(s, "uer_feed_blend_ratio", 0.9)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    now = datetime.now(timezone.utc)
    await _article(db_session, src, now, "A")
    await _article(db_session, src, now - timedelta(days=1), "B")
    await _article(db_session, src, now - timedelta(days=2), "C")
    d = await _article(db_session, src, now - timedelta(days=3), "D-followed")  # oldest
    await _follow_articles_entity(db_session, d)

    page1 = [it["title"] for it in (await aclient.get("/feed?per_page=2&page=1")).json()["articles"]]
    assert "D-followed" in page1  # relevance pulled the oldest item onto page 1

    monkeypatch.setattr(s, "uer_enabled", False)
    page1_off = [it["title"] for it in (await aclient.get("/feed?per_page=2&page=1")).json()["articles"]]
    assert "D-followed" not in page1_off  # recency-only → oldest is on the last page


@pytest.mark.asyncio
async def test_feed_on_zero_uer_identical_to_off(aclient, db_session, monkeypatch):
    """Enabled but the user has no follows/feedback → pure recency, same as off (no-op invariant)."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    now = datetime.now(timezone.utc)
    await _article(db_session, src, now, "One")
    await _article(db_session, src, now - timedelta(days=1), "Two")
    await _article(db_session, src, now - timedelta(days=2), "Three")
    body = (await aclient.get("/feed?per_page=50")).json()
    assert [it["title"] for it in body["articles"]] == ["One", "Two", "Three"]


@pytest.mark.asyncio
async def test_feed_on_no_n_plus_one(aclient, db_session, engine, monkeypatch):
    """The on-path adds only bounded aggregates — query count stays constant in the article count (no
    per-article N+1). WS-5 adds one-hop expansion: a couple more single IN-clause queries (seed
    affinities + graph neighbours), still O(1) in the pool size."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    now = datetime.now(timezone.utc)
    clustered = []
    for i in range(25):
        a = await _article(db_session, src, now - timedelta(hours=i), f"Item {i}")
        if i < 4:
            clustered.append(a)
    await _follow_articles_entity(db_session, *clustered)

    counter = {"n": 0}

    def _before(conn, cur, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            counter["n"] += 1

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _before)
    try:
        resp = await aclient.get("/feed?per_page=50")
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before)

    assert resp.status_code == 200
    # Phase 4: the 4 clustered articles collapse to one row → 21 standalone + 1 cluster rep = 22.
    assert len(resp.json()["articles"]) == 22
    assert counter["n"] <= 15, f"feed (personalized) issued {counter['n']} SELECTs (possible N+1)"
