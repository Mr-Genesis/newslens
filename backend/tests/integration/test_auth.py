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
