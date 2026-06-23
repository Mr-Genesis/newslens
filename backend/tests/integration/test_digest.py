"""Wave C: 'while you were away' digest — recent, gated by last_seen, LLM-free. TDD."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import StoryCluster, User


async def _user_lastseen(db, dt):
    u = await db.get(User, 1)
    if u is None:
        u = User(id=1, locale="IN")
        db.add(u)
    u.last_seen_at = dt
    await db.flush()
    return u


async def _cluster(db, title, impact_json=None):
    c = StoryCluster(title=title, summary="s", impact_json=impact_json)
    db.add(c)
    await db.flush()
    return c


@pytest.mark.asyncio
async def test_digest_returns_recent_since_last_seen(aclient, db_session):
    await _user_lastseen(db_session, datetime.now(timezone.utc) - timedelta(hours=48))
    await _cluster(db_session, "Story One")
    await _cluster(db_session, "Story Two")
    b = (await aclient.get("/digest")).json()
    assert b["count"] >= 2
    assert any(i["title"] == "Story One" for i in b["items"])


@pytest.mark.asyncio
async def test_digest_empty_after_marking_seen(aclient, db_session):
    await _user_lastseen(db_session, datetime.now(timezone.utc) - timedelta(hours=48))
    await _cluster(db_session, "X")
    first = (await aclient.get("/digest")).json()
    assert first["count"] >= 1  # this visit marks last_seen = now
    second = (await aclient.get("/digest")).json()
    assert second["count"] == 0  # nothing new since the previous visit


@pytest.mark.asyncio
async def test_digest_includes_cached_impact_headline(aclient, db_session):
    await _user_lastseen(db_session, datetime.now(timezone.utc) - timedelta(hours=48))
    await _cluster(
        db_session, "H",
        impact_json={"persona:abc": {"source_hash": "s", "data": {"headline": "This affects you."}}},
    )
    b = (await aclient.get("/digest")).json()
    item = next(i for i in b["items"] if i["title"] == "H")
    assert item["headline"] == "This affects you."
