"""A newly-created topic interest surfaces content within seconds: backfill_topic_articles
retroactively tags existing articles (pgvector NN + keyword), and PUT /profile schedules that backfill
for brand-new topics only."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import (
    Article,
    ArticleTopic,
    EmbeddingStatus,
    Source,
    SourceType,
    Topic,
    User,
    UserPreference,
)
from app.services import fetcher

DEFAULT_USER = 1
_n = 0


def _vec(idx, dim=768):
    v = [0.0] * dim
    v[idx] = 1.0
    return v  # one-hot → cosine distance 0 to itself, 1.0 to any other one-hot (straddles the 0.6 gate)


async def _src(db):
    global _n
    _n += 1
    s = Source(name=f"TB{_n}", url=f"https://tb/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _article(db, src, title, vec):
    a = Article(
        title=title, url=f"https://tb/{title}/{id(title)}", source_id=src.id,
        embedding=vec, embedding_status=EmbeddingStatus.complete,
    )
    db.add(a)
    await db.flush()
    return a


async def _ensure_user(db, uid=DEFAULT_USER):
    if not await db.get(User, uid):
        db.add(User(id=uid))
        await db.flush()


@pytest.mark.asyncio
async def test_backfill_tags_semantically_near_articles_only(db_session):
    src = await _src(db_session)
    near = await _article(db_session, src, "near story", _vec(0))
    far = await _article(db_session, src, "far story", _vec(1))
    topic = Topic(name="Some Topic", embedding=_vec(0))
    db_session.add(topic)
    await db_session.flush()

    created = await fetcher.backfill_topic_articles(db_session, topic.id)

    tagged = set(
        (
            await db_session.execute(
                select(ArticleTopic.article_id).where(ArticleTopic.topic_id == topic.id)
            )
        ).scalars().all()
    )
    assert near.id in tagged  # cosine distance 0 < 0.6
    assert far.id not in tagged  # cosine distance 1.0 >= 0.6
    assert created == 1


@pytest.mark.asyncio
async def test_backfill_keyword_fallback_on_topic_name(db_session):
    src = await _src(db_session)
    # Embedding is orthogonal to the topic (no semantic match), but the title contains the name.
    art = await _article(db_session, src, "Bitcoin hits a new high today", _vec(5))
    topic = Topic(name="Bitcoin", embedding=_vec(9))
    db_session.add(topic)
    await db_session.flush()

    await fetcher.backfill_topic_articles(db_session, topic.id)

    tagged = set(
        (
            await db_session.execute(
                select(ArticleTopic.article_id).where(ArticleTopic.topic_id == topic.id)
            )
        ).scalars().all()
    )
    assert art.id in tagged  # matched by the whole-word keyword pass, not the semantic pass


@pytest.mark.asyncio
async def test_schedule_topic_backfill_dedupes_and_runs_once(monkeypatch):
    calls = []

    async def fake_backfill(session, tid):
        calls.append(tid)

    monkeypatch.setattr(fetcher, "backfill_topic_articles", fake_backfill)
    fetcher._topic_backfill_scheduled.discard(4242)

    t1 = fetcher.schedule_topic_backfill(4242)
    t2 = fetcher.schedule_topic_backfill(4242)  # deduped while in flight
    assert t1 is not None
    assert t2 is None
    assert t1 in fetcher._topic_backfill_tasks  # strong ref held → not GC-cancellable

    await t1
    assert calls == [4242]
    assert 4242 not in fetcher._topic_backfill_scheduled
    assert t1 not in fetcher._topic_backfill_tasks


@pytest.mark.asyncio
async def test_schedule_topic_backfill_gated_off(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "topic_backfill_enabled", False)
    fetcher._topic_backfill_scheduled.discard(7)
    assert fetcher.schedule_topic_backfill(7) is None


@pytest.mark.asyncio
async def test_put_profile_schedules_backfill_for_new_topics_only(aclient, db_session, monkeypatch):
    scheduled = []
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: scheduled.append(tid))

    await _ensure_user(db_session)
    existing = Topic(name="Existing Topic")
    db_session.add(existing)
    await db_session.flush()

    r = await aclient.put("/profile", json={"interests": ["Existing Topic", "Brand New Topic"]})
    assert r.status_code == 200

    # the pre-existing topic already has (its) content → NOT scheduled; only the brand-new one is
    assert len(scheduled) == 1
    assert existing.id not in scheduled


@pytest.mark.asyncio
async def test_keyword_pass_scans_the_newest_candidates(db_session):
    # Review #1: the keyword ilike LIMIT must ORDER BY fetched_at so the window is the newest N, not an
    # arbitrary heap order (else real matches for a short/common name silently fall outside the window).
    src = await _src(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    arts = []
    for i in range(4):
        a = Article(
            title=f"Rustlang release {i}", url=f"https://tb/rl/{i}", source_id=src.id,
            fetched_at=base + timedelta(days=i),  # increasing recency; no embedding → semantic pass skipped
        )
        db_session.add(a)
        await db_session.flush()
        arts.append(a)
    topic = Topic(name="Rustlang", embedding=_vec(0))  # has an embedding → no generation call
    db_session.add(topic)
    await db_session.flush()

    await fetcher.backfill_topic_articles(db_session, topic.id, limit=2)

    tagged = set(
        (
            await db_session.execute(
                select(ArticleTopic.article_id).where(ArticleTopic.topic_id == topic.id)
            )
        ).scalars().all()
    )
    assert arts[3].id in tagged and arts[2].id in tagged  # the two newest candidates
    assert arts[0].id not in tagged  # oldest is outside the ORDER BY fetched_at DESC LIMIT 2 window


@pytest.mark.asyncio
async def test_backfill_is_idempotent_no_duplicate_rows(db_session):
    # Review #2: a pre-existing (article, topic) row must not crash the backfill or duplicate.
    src = await _src(db_session)
    near = await _article(db_session, src, "near story", _vec(0))
    topic = Topic(name="ZZ Topic", embedding=_vec(0))
    db_session.add(topic)
    await db_session.flush()
    db_session.add(ArticleTopic(article_id=near.id, topic_id=topic.id))  # already tagged
    await db_session.flush()

    await fetcher.backfill_topic_articles(db_session, topic.id)  # must not raise on the duplicate

    count = (
        await db_session.execute(
            select(func.count()).select_from(ArticleTopic).where(ArticleTopic.topic_id == topic.id)
        )
    ).scalar()
    assert count == 1  # no duplicate row


@pytest.mark.asyncio
async def test_backfill_my_topics_endpoint_schedules_all_subscriptions(aclient, db_session, monkeypatch):
    scheduled = []

    def fake_schedule(tid):
        scheduled.append(tid)
        return object()  # non-None → counted as scheduled

    monkeypatch.setattr(fetcher, "schedule_topic_backfill", fake_schedule)
    await _ensure_user(db_session)
    t1 = Topic(name="T1")
    t2 = Topic(name="T2")
    db_session.add_all([t1, t2])
    await db_session.flush()
    db_session.add_all(
        [
            UserPreference(user_id=DEFAULT_USER, topic_id=t1.id, weight=1.0),
            UserPreference(user_id=DEFAULT_USER, topic_id=t2.id, weight=1.0),
        ]
    )
    await db_session.flush()

    r = await aclient.post("/profile/backfill-topics")
    assert r.status_code == 200
    assert r.json() == {"topics": 2, "scheduled": 2}
    assert set(scheduled) == {t1.id, t2.id}
