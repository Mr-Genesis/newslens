"""G2 S8: /search within-tier relevance boost — keyword stays above semantic; off = unchanged."""
from datetime import datetime, timezone

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
    s = Source(name="S", url=f"https://srch/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _kw_article(db, src, title):
    """A keyword-matchable article in its own cluster. Returns (article, cluster)."""
    global _n
    _n += 1
    a = Article(title=title, url=f"https://srch/{_n}/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    cl = StoryCluster(title=title)
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return a, cl


async def _follow(db, art, user_id=1):
    global _n
    _n += 1
    e = Entity(canonical_name="Z", name_norm=f"z-{_n}", kind="org")
    db.add(e)
    await db.flush()
    db.add(ArticleEntity(article_id=art.id, entity_id=e.id, salience=0.5))
    db.add(UserEntityRelevance(user_id=user_id, entity_id=e.id, source="follow",
                               engagement_raw=1.0, last_event_at=datetime.now(timezone.utc)))
    await db.flush()


@pytest.mark.asyncio
async def test_search_on_boosts_followed_cluster(aclient, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    await _kw_article(db_session, src, "Acme alpha")        # X (inserted first)
    ay, _ = await _kw_article(db_session, src, "Acme beta")  # Y
    await _follow(db_session, ay)
    res = (await aclient.get("/search?q=Acme")).json()["results"]
    assert res[0]["id"] == ay.id  # followed cluster boosted to the top within tier


@pytest.mark.asyncio
async def test_search_off_ignores_follow(aclient, db_session, monkeypatch):
    from app.config import settings as s
    await _ensure_user1(db_session)
    src = await _src(db_session)
    await _kw_article(db_session, src, "Acme alpha")
    ay, _ = await _kw_article(db_session, src, "Acme beta")
    await _follow(db_session, ay)

    monkeypatch.setattr(s, "uer_enabled", True)
    on_first = (await aclient.get("/search?q=Acme")).json()["results"][0]["id"]
    monkeypatch.setattr(s, "uer_enabled", False)
    off_first = (await aclient.get("/search?q=Acme")).json()["results"][0]["id"]
    assert on_first == ay.id       # boosted when on
    assert off_first != ay.id      # off → the follow has no effect


@pytest.mark.asyncio
async def test_search_zero_uer_on_equals_off(aclient, db_session, monkeypatch):
    from app.config import settings as s
    await _ensure_user1(db_session)
    src = await _src(db_session)
    await _kw_article(db_session, src, "Acme alpha")
    await _kw_article(db_session, src, "Acme beta")  # no follows anywhere

    monkeypatch.setattr(s, "uer_enabled", True)
    on = [r["id"] for r in (await aclient.get("/search?q=Acme")).json()["results"]]
    monkeypatch.setattr(s, "uer_enabled", False)
    off = [r["id"] for r in (await aclient.get("/search?q=Acme")).json()["results"]]
    assert on == off  # no relevance signal → identical ordering
