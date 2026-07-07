"""Unify interests ↔ topic follows: following a topic makes it an interest (+ backfill), unfollowing
drops the interest, and setting profile interests keeps the topic follows ("News You Follow") in sync."""
import pytest

from app.models import User
from app.services import fetcher

DEFAULT_USER = 1


async def _ensure_user(db, uid=DEFAULT_USER):
    if not await db.get(User, uid):
        db.add(User(id=uid))
        await db.flush()


@pytest.mark.asyncio
async def test_follow_topic_creates_interest_and_schedules_backfill(aclient, db_session, monkeypatch):
    scheduled = []
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: scheduled.append(tid))
    await _ensure_user(db_session)

    r = await aclient.post("/follows", json={"kind": "topic", "value": "Quantum Computing"})
    assert r.status_code == 201
    # following a topic makes it an interest (get_profile reads UserPreference → Topic names)
    assert "Quantum Computing" in (await aclient.get("/profile")).json()["interests"]
    # and schedules the article backfill so the rail has content
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_unfollow_topic_removes_interest(aclient, db_session, monkeypatch):
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)

    fid = (await aclient.post("/follows", json={"kind": "topic", "value": "Fusion Energy"})).json()["id"]
    assert "Fusion Energy" in (await aclient.get("/profile")).json()["interests"]

    assert (await aclient.delete(f"/follows/{fid}")).status_code == 204
    assert "Fusion Energy" not in (await aclient.get("/profile")).json()["interests"]


@pytest.mark.asyncio
async def test_setting_interests_syncs_topic_follows(aclient, db_session, monkeypatch):
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)

    async def topic_follows():
        rows = (await aclient.get("/follows")).json()
        return {f["value"] for f in rows if f["kind"] == "topic"}

    await aclient.put("/profile", json={"interests": ["Alpha Topic", "Beta Topic"]})
    assert await topic_follows() == {"Alpha Topic", "Beta Topic"}  # interests → follows

    # drop Beta, add Gamma → follows reconcile to match the new interest set
    await aclient.put("/profile", json={"interests": ["Alpha Topic", "Gamma Topic"]})
    assert await topic_follows() == {"Alpha Topic", "Gamma Topic"}
