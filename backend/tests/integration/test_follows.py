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
