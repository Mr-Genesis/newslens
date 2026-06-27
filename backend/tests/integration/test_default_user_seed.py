"""Bug-3 regression: the default-user seed must populate every NOT NULL `users` column.

`locale`, `depth_pref`, `persona_version`, `watchlist` carry only a MODEL-side default — under a
create_all schema they have no server_default, so a raw `INSERT INTO users (id) VALUES (1)` raises
NotNullViolation and aborts init_db before topics are seeded. init_db now seeds via the ORM
(`User(id=1)`), which applies every model default. This guards that path against regression.
"""
from sqlalchemy import select

from app.models import User


async def test_orm_seed_populates_not_null_defaults(db_session):
    """Constructing User() with only the id fills the NOT NULL columns a raw INSERT would omit —
    exactly what init_db's default-user seed relies on (app/main.py)."""
    db_session.add(User(id=4242))
    await db_session.flush()

    u = (await db_session.execute(select(User).where(User.id == 4242))).scalar_one()
    assert u.locale == "IN"
    assert u.depth_pref == "standard"
    assert u.persona_version == 1
    assert u.watchlist == []
    assert u.created_at is not None
