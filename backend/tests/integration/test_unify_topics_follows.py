"""Unify interests ↔ topic follows: following a topic makes it an interest (+ backfill), unfollowing
drops the interest, and setting profile interests keeps the topic follows ("News You Follow") in sync."""
import pytest
from sqlalchemy import func, select

from app.models import Follow, Topic, User, UserPreference
from app.services import fetcher

DEFAULT_USER = 1


async def _ensure_user(db, uid=DEFAULT_USER):
    if not await db.get(User, uid):
        db.add(User(id=uid))
        await db.flush()


async def _legacy_topic_follow(db, name, uid=DEFAULT_USER):
    """A topic Follow + its Topic row but NO UserPreference — the pre-unify prod shape
    (topics were follows-only). Used to test that re-follow / backfill repair the missing interest."""
    t = Topic(name=name)
    db.add(t)
    await db.flush()
    db.add(Follow(user_id=uid, kind="topic", value=name))
    await db.flush()
    return t


async def _interests(aclient):
    return set((await aclient.get("/profile")).json()["interests"])


async def _topic_follow_values(aclient):
    rows = (await aclient.get("/follows")).json()
    return [f["value"] for f in rows if f["kind"] == "topic"]


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


# ── Review fixes (adversarial review of 5762739) ──


@pytest.mark.asyncio
async def test_refollow_existing_topic_repairs_missing_interest(aclient, db_session, monkeypatch):
    """Finding 1: the idempotent early-return must SELF-HEAL — re-following a topic that has a Follow
    but no UserPreference (the legacy prod shape) creates the missing interest instead of no-op'ing."""
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)
    await _legacy_topic_follow(db_session, "Legacy Topic")
    await db_session.commit()
    assert "Legacy Topic" not in await _interests(aclient)  # precondition: orphan follow, no interest

    r = await aclient.post("/follows", json={"kind": "topic", "value": "Legacy Topic"})
    assert r.status_code == 201
    assert "Legacy Topic" in await _interests(aclient)  # re-follow repaired the interest
    assert await _topic_follow_values(aclient) == ["Legacy Topic"]  # no duplicate follow


@pytest.mark.asyncio
async def test_follow_topic_is_case_insensitive_no_duplicates(aclient, db_session, monkeypatch):
    """Finding 2: following 'AI' then 'ai' must NOT create a second Topic / interest / follow / rail —
    write paths match case-insensitively and reuse the canonical Topic.name."""
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)

    assert (await aclient.post("/follows", json={"kind": "topic", "value": "AI"})).status_code == 201
    assert (await aclient.post("/follows", json={"kind": "topic", "value": "ai"})).status_code == 201

    assert await _topic_follow_values(aclient) == ["AI"]  # one canonical follow, not two
    assert await _interests(aclient) == {"AI"}  # one canonical interest
    topic_rows = (
        await db_session.execute(select(func.count()).select_from(Topic).where(func.lower(Topic.name) == "ai"))
    ).scalar()
    assert topic_rows == 1  # one Topic row, not two case-variants


@pytest.mark.asyncio
async def test_delete_topic_follow_removes_interest_case_insensitively(aclient, db_session, monkeypatch):
    """Finding 2 (delete path): a follow whose value differs in case from the Topic.name must still
    resolve the Topic and drop the interest."""
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)
    t = Topic(name="Robotics")
    db_session.add(t)
    await db_session.flush()
    db_session.add(UserPreference(user_id=DEFAULT_USER, topic_id=t.id, weight=1.0))
    f = Follow(user_id=DEFAULT_USER, kind="topic", value="robotics")  # lower-case value vs 'Robotics'
    db_session.add(f)
    await db_session.flush()
    await db_session.commit()

    assert (await aclient.delete(f"/follows/{f.id}")).status_code == 204
    assert "Robotics" not in await _interests(aclient)


@pytest.mark.asyncio
async def test_backfill_topics_reconciles_legacy_follow_without_interest(aclient, db_session, monkeypatch):
    """Finding 5: POST /profile/backfill-topics must repair EVERY legacy topic follow that has no
    interest (e.g. user 1's 7 topics seeded as follows before unify), inserting the missing UserPreference."""
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)
    await _legacy_topic_follow(db_session, "Seeded A")
    await _legacy_topic_follow(db_session, "Seeded B")
    await db_session.commit()
    assert await _interests(aclient) == set()  # legacy follows, zero interests

    r = await aclient.post("/profile/backfill-topics")
    assert r.status_code == 200
    assert await _interests(aclient) == {"Seeded A", "Seeded B"}  # follows reconciled into interests


# ── Swipe path: a POSITIVE swipe mirrors the interest into a topic follow ──
# (the item deferred by the 5762739 adversarial review — "needs a negative-swipe product call")


async def _article_with_topic(db, topic_name):
    """Seed a Source + Article tagged to a NEW Topic, so a swipe on that article has a primary topic
    to mirror. Unique topic_name per test keeps the process-level rails cache from leaking rails across
    tests (the negative assertions stay meaningful even on a stale-cache hit)."""
    from datetime import datetime, timezone

    from app.models import Article, ArticleTopic, Source, SourceType

    src = Source(
        name=f"src-{topic_name}", url=f"https://{topic_name}.example",
        rss_url=f"https://{topic_name}.example/rss", source_type=SourceType.wire,
        region="global", category="world",
    )
    db.add(src)
    await db.flush()
    topic = Topic(name=topic_name)
    db.add(topic)
    await db.flush()
    art = Article(
        title=f"{topic_name} headline", url=f"https://{topic_name}.example/a1",
        source_id=src.id, snippet="A snippet.", published_at=datetime.now(timezone.utc),
    )
    db.add(art)
    await db.flush()
    db.add(ArticleTopic(article_id=art.id, topic_id=topic.id, relevance_score=1.0))
    await db.flush()
    return art, topic


async def _rail_keys(aclient):
    """Set of (kind, value) for the "News You Follow" rails — one per rail-able follow (even empty)."""
    rails = (await aclient.get("/follows/rails")).json()["rails"]
    return {(r["kind"], r["value"]) for r in rails}


@pytest.mark.asyncio
async def test_right_swipe_creates_interest_and_topic_follow(aclient, db_session, monkeypatch):
    """Deferred gap from 5762739: a POSITIVE (right) swipe must create BOTH the UserPreference interest
    AND the matching kind='topic' Follow — so a swipe-born interest also earns a "News You Follow" rail
    instead of showing only in Your Topics / chips / feed rank."""
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)
    art, _ = await _article_with_topic(db_session, "Space Exploration")
    await db_session.commit()

    r = await aclient.post("/discover/swipe", json={"article_id": art.id, "direction": "right"})
    assert r.status_code == 204

    assert "Space Exploration" in await _interests(aclient)                 # interest (existing behavior)
    assert await _topic_follow_values(aclient) == ["Space Exploration"]     # topic follow (the fix)
    assert ("topic", "Space Exploration") in await _rail_keys(aclient)      # → surfaces a rail


@pytest.mark.asyncio
async def test_up_swipe_also_creates_topic_follow(aclient, db_session, monkeypatch):
    """The other positive direction (up / save, +0.3) mirrors into a topic follow too — the gate is
    weight_delta > 0, not literally "right"."""
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)
    art, _ = await _article_with_topic(db_session, "Marine Biology")
    await db_session.commit()

    r = await aclient.post("/discover/swipe", json={"article_id": art.id, "direction": "up"})
    assert r.status_code == 204
    assert await _topic_follow_values(aclient) == ["Marine Biology"]


@pytest.mark.asyncio
async def test_left_swipe_creates_no_follow_and_no_rail(aclient, db_session, monkeypatch):
    """A NEGATIVE (left) swipe must NOT create a topic follow nor surface a rail for a topic the user
    swiped AWAY from — even though it still nudges the interest weight (the intentional asymmetry that
    is the whole reason for the weight_delta > 0 gate)."""
    monkeypatch.setattr(fetcher, "schedule_topic_backfill", lambda tid: None)
    await _ensure_user(db_session)
    art, _ = await _article_with_topic(db_session, "Competitive Curling")
    await db_session.commit()

    r = await aclient.post("/discover/swipe", json={"article_id": art.id, "direction": "left"})
    assert r.status_code == 204

    assert await _topic_follow_values(aclient) == []                            # no topic follow
    assert ("topic", "Competitive Curling") not in await _rail_keys(aclient)    # no rail surfaced
    # The interest IS still created (weight max(0, 1-0.2)=0.8): a left swipe nudges personalization but
    # must not promote the topic into "News You Follow".
    assert "Competitive Curling" in await _interests(aclient)
