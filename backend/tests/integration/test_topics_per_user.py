"""GET /topics is per-user: your_topics = the caller's UserPreference subscriptions, explore =
unsubscribed topics with content, trending = top by recent (7d) volume (was "all topics → your_topics")."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Article, ArticleTopic, Source, SourceType, Topic, User, UserPreference

DEFAULT_USER = 1
_n = 0


async def _ensure_user(db, uid=DEFAULT_USER):
    if not await db.get(User, uid):
        db.add(User(id=uid))
        await db.flush()


async def _src(db):
    global _n
    _n += 1
    s = Source(name=f"TS{_n}", url=f"https://tp/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _topic_with_articles(db, src, name, count, days_ago=1):
    t = Topic(name=name)
    db.add(t)
    await db.flush()
    pub = datetime.now(timezone.utc) - timedelta(days=days_ago)
    for i in range(count):
        a = Article(title=f"{name}-{i}", url=f"https://tp/{name}/{i}", source_id=src.id, published_at=pub)
        db.add(a)
        await db.flush()
        db.add(ArticleTopic(article_id=a.id, topic_id=t.id))
    await db.flush()
    return t


@pytest.mark.asyncio
async def test_your_topics_are_the_callers_subscriptions_only(aclient, db_session):
    await _ensure_user(db_session)
    src = await _src(db_session)
    t_sub = await _topic_with_articles(db_session, src, "Subscribed Topic", 2)
    await _topic_with_articles(db_session, src, "Unsubscribed Topic", 3)
    db_session.add(UserPreference(user_id=DEFAULT_USER, topic_id=t_sub.id, weight=1.0))
    await db_session.flush()

    body = (await aclient.get("/topics")).json()
    your = {t["name"] for t in body["your_topics"]}
    explore = {t["name"] for t in body["explore_topics"]}

    assert "Subscribed Topic" in your
    assert "Unsubscribed Topic" not in your  # not subscribed → out of your_topics
    assert "Unsubscribed Topic" in explore  # unsubscribed + has content → explore
    assert "Subscribed Topic" not in explore
    # real article_count carried through
    sub = next(t for t in body["your_topics"] if t["name"] == "Subscribed Topic")
    assert sub["article_count"] == 2


@pytest.mark.asyncio
async def test_no_subscriptions_gives_empty_your_topics(aclient, db_session):
    src = await _src(db_session)
    await _topic_with_articles(db_session, src, "Only Topic", 2)

    body = (await aclient.get("/topics")).json()
    assert body["your_topics"] == []  # caller subscribed to nothing
    assert any(t["name"] == "Only Topic" for t in body["explore_topics"])


@pytest.mark.asyncio
async def test_trending_reflects_recent_volume_only(aclient, db_session):
    src = await _src(db_session)
    await _topic_with_articles(db_session, src, "HotNow", 5, days_ago=1)  # recent
    await _topic_with_articles(db_session, src, "StaleOld", 4, days_ago=30)  # outside the 7d window

    body = (await aclient.get("/topics")).json()
    trending = [t["name"] for t in body["trending_topics"]]
    assert "HotNow" in trending
    assert "StaleOld" not in trending  # old articles don't trend
