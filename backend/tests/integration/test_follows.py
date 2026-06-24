"""Standing follows (/follows) — real-DB integration: CRUD, idempotency, filtering.

MUST RUN IN DOCKER (see tests/integration/conftest.py header)."""
import pytest
from sqlalchemy import func, select

from app.models import Follow


@pytest.mark.asyncio
async def test_follow_crud_roundtrip(aclient, db_session):
    # Starts empty
    r = await aclient.get("/follows")
    assert r.status_code == 200
    assert r.json() == []

    # Follow a topic
    r = await aclient.post("/follows", json={"kind": "topic", "value": "AI"})
    assert r.status_code == 201
    created = r.json()
    assert created["kind"] == "topic"
    assert created["value"] == "AI"
    follow_id = created["id"]

    # Shows up in the list
    r = await aclient.get("/follows")
    assert [f["value"] for f in r.json()] == ["AI"]

    # Unfollow
    r = await aclient.delete(f"/follows/{follow_id}")
    assert r.status_code == 204
    r = await aclient.get("/follows")
    assert r.json() == []


@pytest.mark.asyncio
async def test_follow_is_idempotent_on_user_kind_value(aclient, db_session):
    a = await aclient.post("/follows", json={"kind": "topic", "value": "Climate"})
    b = await aclient.post("/follows", json={"kind": "topic", "value": "Climate"})
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] == b.json()["id"]  # same row, not a duplicate

    count = (
        await db_session.execute(
            select(func.count()).select_from(Follow).where(Follow.value == "Climate")
        )
    ).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_same_value_different_kind_are_distinct(aclient, db_session):
    t = await aclient.post("/follows", json={"kind": "topic", "value": "Tesla"})
    e = await aclient.post("/follows", json={"kind": "entity", "value": "Tesla"})
    assert t.json()["id"] != e.json()["id"]
    r = await aclient.get("/follows")
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_saved_search_kind_supported(aclient, db_session):
    r = await aclient.post(
        "/follows", json={"kind": "saved_search", "value": "opec production cuts"}
    )
    assert r.status_code == 201
    assert r.json()["kind"] == "saved_search"


@pytest.mark.asyncio
async def test_invalid_kind_rejected_400_and_persists_nothing(aclient, db_session):
    r = await aclient.post("/follows", json={"kind": "playlist", "value": "x"})
    assert r.status_code == 400
    r = await aclient.get("/follows")
    assert r.json() == []


@pytest.mark.asyncio
async def test_delete_only_targets_the_requested_id(aclient, db_session):
    """DELETE honors the WHERE id=… (proves it's not deleting an arbitrary row)."""
    keep = (await aclient.post("/follows", json={"kind": "topic", "value": "Keep"})).json()
    drop = (await aclient.post("/follows", json={"kind": "topic", "value": "Drop"})).json()

    r = await aclient.delete(f"/follows/{drop['id']}")
    assert r.status_code == 204

    remaining = (await aclient.get("/follows")).json()
    assert [f["id"] for f in remaining] == [keep["id"]]


@pytest.mark.asyncio
async def test_delete_unknown_id_is_noop_204(aclient, db_session):
    r = await aclient.delete("/follows/123456")
    assert r.status_code == 204
