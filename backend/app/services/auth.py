"""Wave D Phase A: Firebase auth seam (precondition for the per-user graph overlay).

The token verifier is a seam: production verifies a Firebase ID token via firebase-admin (needs
project credentials in env); tests monkeypatch ``verify_firebase_token``. ``resolve_user`` maps a
verified uid to a User row (get-or-create) and falls back to the default single user when no token
is present, so existing endpoints keep working until they are migrated to require auth.
"""
import structlog
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User

logger = structlog.get_logger()

DEFAULT_USER_ID = 1


async def verify_firebase_token(token: str) -> str | None:
    """Verify a Firebase ID token and return its uid, or None if invalid/unverifiable.

    Lazy-imports firebase-admin so the module loads without it; production must initialise the
    Admin SDK at startup with project credentials (env). Tests monkeypatch this function.
    """
    try:
        from firebase_admin import auth as fb_auth  # lazy — only on the real verify path

        decoded = fb_auth.verify_id_token(token)
        return decoded.get("uid")
    except Exception as e:  # noqa: BLE001 — any failure = unverifiable
        logger.debug("firebase_verify_failed", error=str(e))
        return None


async def _get_or_create_default(db: AsyncSession) -> User:
    u = await db.get(User, DEFAULT_USER_ID)
    if u is None:
        u = User(id=DEFAULT_USER_ID, locale="IN")
        db.add(u)
        await db.flush()
    return u


async def resolve_user(db: AsyncSession, authorization: str | None) -> User:
    """Authorization header → User. No header → default single user (back-compat). Present-but-
    invalid token → 401 (never silently fall through to another identity)."""
    if not authorization:
        return await _get_or_create_default(db)
    token = authorization.split(" ", 1)[1] if " " in authorization else authorization
    uid = await verify_firebase_token(token)
    if not uid:
        raise HTTPException(status_code=401, detail="invalid auth token")
    u = (
        await db.execute(select(User).where(User.firebase_uid == uid))
    ).scalar_one_or_none()
    if u is None:
        u = User(firebase_uid=uid, locale="IN")
        db.add(u)
        await db.flush()
    return u


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency. New per-user endpoints depend on this; existing endpoints are
    migrated incrementally (the no-token fallback keeps them working meanwhile)."""
    return await resolve_user(db, authorization)
