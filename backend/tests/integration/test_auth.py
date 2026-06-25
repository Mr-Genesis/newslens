"""Wave D Phase A: Firebase auth seam — token → user, get-or-create, back-compat. TDD.

The Firebase verifier is mocked (no live keys needed to build/test the seam)."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import User
from app.services import auth


@pytest.mark.asyncio
async def test_resolve_user_creates_user_for_new_uid(db_session, monkeypatch):
    async def fake_verify(token):
        return "firebase-abc"

    monkeypatch.setattr(auth, "verify_firebase_token", fake_verify)
    u = await auth.resolve_user(db_session, "Bearer sometoken")
    assert u.firebase_uid == "firebase-abc"
    # idempotent: same uid → same user row
    u2 = await auth.resolve_user(db_session, "Bearer sometoken")
    assert u2.id == u.id
    rows = (await db_session.execute(
        select(User).where(User.firebase_uid == "firebase-abc"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_resolve_user_falls_back_to_default_without_token(db_session):
    u = await auth.resolve_user(db_session, None)
    assert u.id == 1  # back-compat single user


@pytest.mark.asyncio
async def test_resolve_user_rejects_invalid_token(db_session, monkeypatch):
    async def fake_verify(token):
        return None  # invalid / unverifiable

    monkeypatch.setattr(auth, "verify_firebase_token", fake_verify)
    with pytest.raises(HTTPException) as ei:
        await auth.resolve_user(db_session, "Bearer badtoken")
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_default_user_without_token(aclient):
    b = (await aclient.get("/auth/me")).json()
    assert b["id"] == 1  # unauthenticated → default user (back-compat)


@pytest.mark.asyncio
async def test_auth_me_with_valid_token(aclient, monkeypatch):
    async def fake_verify(token):
        return "me-uid-1"

    monkeypatch.setattr(auth, "verify_firebase_token", fake_verify)
    r = await aclient.get("/auth/me", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json()["firebase_uid"] == "me-uid-1"


@pytest.mark.asyncio
async def test_auth_me_rejects_bad_token(aclient, monkeypatch):
    async def fake_verify(token):
        return None

    monkeypatch.setattr(auth, "verify_firebase_token", fake_verify)
    r = await aclient.get("/auth/me", headers={"Authorization": "Bearer bad"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_anonymous_allowed_when_auth_not_required(aclient):
    # Default (auth_required=False): a gated endpoint serves the default user, no 401.
    r = await aclient.get("/follows")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_required_rejects_anonymous(aclient, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "auth_required", True)
    r = await aclient.get("/follows")  # gated endpoint, no Authorization header
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_follows_scoped_to_authenticated_user(aclient, monkeypatch):
    """Cutover proof: a gated endpoint reads/writes the AUTHENTICATED user's rows, and the
    default (anonymous) user cannot see them."""
    async def fake_verify(token):
        return "u-follow-scope"

    monkeypatch.setattr(auth, "verify_firebase_token", fake_verify)
    h = {"Authorization": "Bearer x"}
    created = await aclient.post("/follows", json={"kind": "topic", "value": "Quantum"}, headers=h)
    assert created.status_code == 201
    mine = (await aclient.get("/follows", headers=h)).json()
    assert any(f["value"] == "Quantum" for f in mine)
    # Anonymous (default user) must NOT see the authenticated user's follow.
    others = (await aclient.get("/follows")).json()
    assert not any(f["value"] == "Quantum" for f in others)


@pytest.mark.asyncio
async def test_firebase_uid_unique_constraint(db_session):
    """DB-level guard: two rows can't share a firebase_uid (the get-or-create race backstop)."""
    from sqlalchemy.exc import IntegrityError

    db_session.add(User(firebase_uid="dup-uid", locale="IN"))
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():  # isolate the failure to a savepoint
            db_session.add(User(firebase_uid="dup-uid", locale="IN"))
    # ...but multiple NULLs are allowed (default user + legacy rows coexist)
    async with db_session.begin_nested():
        db_session.add(User(firebase_uid=None, locale="IN"))
        db_session.add(User(firebase_uid=None, locale="IN"))
