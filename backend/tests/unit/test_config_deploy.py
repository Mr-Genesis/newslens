"""Deploy-schema config: init_db_create_all gates the dev-only create_all bootstrap.

Prod sets INIT_DB_CREATE_ALL=false so Alembic owns the schema; create_all CREATEs missing tables but
can never ALTER an existing one to add a column — the drift that 500'd every authed endpoint in prod.
"""
from app.config import Settings


def test_init_db_create_all_defaults_true(monkeypatch):
    """Default ON so local dev / tests keep bootstrapping the schema without running migrations."""
    monkeypatch.delenv("INIT_DB_CREATE_ALL", raising=False)
    assert Settings().init_db_create_all is True


def test_init_db_create_all_env_off(monkeypatch):
    """Prod (and any Alembic-owned DB) turns it OFF via env so create_all never runs there."""
    monkeypatch.setenv("INIT_DB_CREATE_ALL", "false")
    assert Settings().init_db_create_all is False


def test_sync_url_derives_from_database_url(monkeypatch):
    """Regression: prod sets only DATABASE_URL. database_url_sync MUST derive from it (psycopg2 driver,
    same host) and NEVER fall back to the localhost default — else `alembic upgrade head` at deploy
    time migrates the wrong database. Guards the empty-string default in Settings.database_url_sync."""
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.prod.example.com:5432/newslens")
    s = Settings()
    assert "db.prod.example.com" in s.database_url_sync
    assert "localhost" not in s.database_url_sync
    assert s.database_url_sync.startswith("postgresql://")  # psycopg2 (sync) driver
    assert "+asyncpg" not in s.database_url_sync           # not the async driver
    # And the async URL is the asyncpg form of the same host (no cross-wiring).
    assert s.database_url == "postgresql+asyncpg://u:p@db.prod.example.com:5432/newslens"


def test_explicit_sync_url_overrides_derivation(monkeypatch):
    """An explicit DATABASE_URL_SYNC still wins (docker-compose sets both)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@async-host:5432/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://u:p@sync-host:5432/db")
    s = Settings()
    assert "sync-host" in s.database_url_sync
