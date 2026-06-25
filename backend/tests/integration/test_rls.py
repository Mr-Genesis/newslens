"""Wave D Phase A: Postgres Row-Level Security isolates per-user tables by the app.user_id GUC.

RLS only bites for a NON-superuser role. The dev/test `newslens` role is a superuser (rolbypassrls),
so it bypasses RLS entirely — therefore these tests SET ROLE into a restricted probe role to prove
the policy actually enforces. In production the app must connect as a non-superuser role for RLS to
activate; the explicit current_user_id() filter in the routes is the always-on primary control.
"""
import pytest
from sqlalchemy import select, text

from app.models import (
    Article, EmbeddingStatus, FeedbackType, Source, SourceType, User, UserFeedback,
)

_MAKE_PROBE = """
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
    REVOKE ALL ON user_feedback FROM {role};
    REVOKE ALL ON SCHEMA public FROM {role};
    DROP ROLE {role};
  END IF;
  CREATE ROLE {role} NOLOGIN;
  GRANT USAGE ON SCHEMA public TO {role};
  GRANT SELECT ON user_feedback TO {role};
END $$;
"""


async def _seed_article(db):
    src = Source(name="S", url="https://rls/x", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    art = Article(title="T", url="https://rls/x/a", source_id=src.id,
                  embedding_status=EmbeddingStatus.complete)
    db.add(art)
    await db.flush()
    return art


@pytest.mark.asyncio
async def test_rls_isolates_user_feedback_for_restricted_role(db_session):
    db_session.add_all([User(id=501, locale="IN"), User(id=502, locale="IN")])
    art = await _seed_article(db_session)
    db_session.add(UserFeedback(user_id=501, article_id=art.id, feedback_type=FeedbackType.save))
    await db_session.flush()

    await db_session.execute(text(_MAKE_PROBE.format(role="rls_probe")))
    try:
        await db_session.execute(text("SET ROLE rls_probe"))
        await db_session.execute(text("SELECT set_config('app.user_id', '502', true)"))
        # Raw select, no explicit user filter — RLS must hide 501's row from user 502.
        seen = (await db_session.execute(select(UserFeedback))).scalars().all()
        assert not any(f.user_id == 501 for f in seen)

        await db_session.execute(text("SELECT set_config('app.user_id', '501', true)"))
        seen501 = (await db_session.execute(select(UserFeedback))).scalars().all()
        assert any(f.user_id == 501 for f in seen501)
    finally:
        try:
            await db_session.execute(text("RESET ROLE"))
        except Exception:
            pass  # don't mask the real assertion/SQL error from the try block


@pytest.mark.asyncio
async def test_rls_permissive_when_guc_unset(db_session):
    # Unset GUC (background jobs reading the owner's key, direct-DB) → policy permissive.
    db_session.add(User(id=503, locale="IN"))
    art = await _seed_article(db_session)
    db_session.add(UserFeedback(user_id=503, article_id=art.id, feedback_type=FeedbackType.save))
    await db_session.flush()

    await db_session.execute(text(_MAKE_PROBE.format(role="rls_probe2")))
    try:
        await db_session.execute(text("SET ROLE rls_probe2"))
        await db_session.execute(text("SELECT set_config('app.user_id', NULL, true)"))
        seen = (await db_session.execute(
            select(UserFeedback).where(UserFeedback.user_id == 503))).scalars().all()
        assert len(seen) == 1  # NULL GUC → bypass → visible
    finally:
        try:
            await db_session.execute(text("RESET ROLE"))
        except Exception:
            pass  # don't mask the real assertion/SQL error from the try block
