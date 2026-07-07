"""Wave C: standing follows CRUD + uniqueness. TDD."""
import pytest

from app.models import User


async def _user(db):
    u = await db.get(User, 1)
    if u is None:
        u = User(id=1, locale="IN")
        db.add(u)
        await db.flush()
    return u


@pytest.mark.asyncio
async def test_create_and_list_follow(aclient, db_session):
    await _user(db_session)
    r = await aclient.post("/follows", json={"kind": "topic", "value": "AI"})
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "topic" and body["value"] == "AI"
    lst = (await aclient.get("/follows")).json()
    assert any(f["value"] == "AI" for f in lst)


@pytest.mark.asyncio
async def test_follow_is_idempotent(aclient, db_session):
    await _user(db_session)
    await aclient.post("/follows", json={"kind": "entity", "value": "NVDA"})
    await aclient.post("/follows", json={"kind": "entity", "value": "NVDA"})
    same = [f for f in (await aclient.get("/follows")).json() if f["value"] == "NVDA"]
    assert len(same) == 1  # uniqueness — no duplicate


@pytest.mark.asyncio
async def test_delete_follow(aclient, db_session):
    await _user(db_session)
    fid = (await aclient.post("/follows", json={"kind": "topic", "value": "Markets"})).json()["id"]
    r = await aclient.delete(f"/follows/{fid}")
    assert r.status_code == 204
    assert all(f["id"] != fid for f in (await aclient.get("/follows")).json())


@pytest.mark.asyncio
async def test_follow_rejects_invalid_kind(aclient, db_session):
    await _user(db_session)
    r = await aclient.post("/follows", json={"kind": "bogus", "value": "x"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_saved_search_redirects_to_existing_topic_follow(aclient, db_session):
    """Write-side dedupe: when a topic follow already covers a value, creating a saved_search on the
    SAME value (case-insensitively) must NOT mint a redundant row — it returns the existing topic
    follow. Prevents the duplicate-rail collision at the source (complements rails._dedupe_follows)."""
    await _user(db_session)
    topic = (await aclient.post("/follows", json={"kind": "topic", "value": "AI"})).json()

    # "Follow this search: ai" — same value, different case — must resolve to the existing topic row.
    r = await aclient.post("/follows", json={"kind": "saved_search", "value": "ai"})
    assert r.status_code == 201
    assert r.json()["id"] == topic["id"]      # redirected, not a new row
    assert r.json()["kind"] == "topic"        # kept the precise topic follow

    follows = (await aclient.get("/follows")).json()
    assert [f["kind"] for f in follows] == ["topic"]              # exactly one follow, no saved_search
    assert not any(f["kind"] == "saved_search" for f in follows)


@pytest.mark.asyncio
async def test_saved_search_still_created_when_no_topic_collision(aclient, db_session):
    """Guard is narrow: a saved_search whose value no topic/entity follow covers is created normally."""
    await _user(db_session)
    r = await aclient.post("/follows", json={"kind": "saved_search", "value": "US Iran war"})
    assert r.status_code == 201
    assert r.json()["kind"] == "saved_search"
    assert any(f["kind"] == "saved_search" and f["value"] == "US Iran war"
               for f in (await aclient.get("/follows")).json())
