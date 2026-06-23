"""E★ foundation: prove the pgvector integration harness works end-to-end."""
import os
import pathlib

import pytest
from sqlalchemy import create_engine, func, inspect, select, text

from app.config import settings
from app.models import (
    Article,
    ClusterArticle,
    EmbeddingStatus,
    Source,
    SourceType,
    StoryCluster,
)

# All tables the baseline migration is expected to create.
EXPECTED_TABLES = {
    "sources",
    "story_clusters",
    "topics",
    "users",
    "articles",
    "user_preferences",
    "user_settings",
    "article_topics",
    "cluster_articles",
    "user_feedback",
}

# backend/ root (contains alembic.ini + migrations/), two levels up from this file.
_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _alembic_config():
    """Build an Alembic Config pinned to this project's alembic.ini + sync URL."""
    from alembic.config import Config

    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url_sync)
    return cfg


def _reset_public_schema():
    """Drop + recreate the public schema so the DB is empty before migrating."""
    sync_engine = create_engine(settings.database_url_sync, future=True)
    with sync_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    return sync_engine


@pytest.mark.asyncio
async def test_pgvector_extension_available(db_session):
    v = (
        await db_session.execute(
            text("select extversion from pg_extension where extname='vector'")
        )
    ).scalar()
    assert v is not None


@pytest.mark.asyncio
async def test_create_and_query_cluster(db_session):
    src = Source(
        name="Reuters", url="https://reuters.com/u1", rss_url="https://reuters.com/rss",
        source_type=SourceType.wire, is_paywalled=False,
    )
    db_session.add(src)
    await db_session.flush()
    art = Article(
        title="EU AI Act", snippet="x", url="https://reuters.com/a1",
        source_id=src.id, embedding_status=EmbeddingStatus.pending,
    )
    db_session.add(art)
    await db_session.flush()
    cl = StoryCluster(title="Cluster", summary="s")
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()

    got = (await db_session.execute(select(Article).where(Article.id == art.id))).scalar_one()
    assert got.title == "EU AI Act"
    n = (
        await db_session.execute(
            select(func.count()).select_from(ClusterArticle).where(
                ClusterArticle.cluster_id == cl.id
            )
        )
    ).scalar()
    assert n == 1


@pytest.mark.asyncio
async def test_embedding_column_accepts_vector(db_session):
    src = Source(name="S", url="https://s.example/u2", source_type=SourceType.other)
    db_session.add(src)
    await db_session.flush()
    vec = [0.0] * settings.embedding_dimensions
    vec[0] = 1.0
    art = Article(
        title="V", url="https://s.example/v", source_id=src.id,
        embedding=vec, embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(art)
    await db_session.flush()
    got = (await db_session.execute(select(Article).where(Article.id == art.id))).scalar_one()
    assert got.embedding is not None


@pytest.mark.asyncio
async def test_isolation_rolls_back_between_tests(db_session):
    # Each test's writes are rolled back; the table is empty at the start of every test.
    n = (await db_session.execute(select(func.count()).select_from(Source))).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_fake_llm_seam(fake_llm, db_session):
    from app.services import embeddings, llm
    out = await llm.generate("hi")
    emb = await embeddings.generate_embedding("hi")
    assert out == "STUB SUMMARY"
    assert len(emb) == settings.embedding_dimensions
    assert fake_llm["generate"] == 1 and fake_llm["embed"] == 1


# ── Alembic baseline ↔ models contract (E foundation) ──
# These reset the public schema and drive Alembic directly, so they are synchronous
# (the sync psycopg2 driver is what alembic env.py uses). They share the integration
# suite's DB requirement and only run in the Docker harness like the rest of this file.
@pytest.mark.asyncio
async def test_alembic_upgrade_from_empty_creates_all_tables():
    from alembic import command

    _reset_public_schema()
    command.upgrade(_alembic_config(), "head")

    sync_engine = create_engine(settings.database_url_sync, future=True)
    insp = inspect(sync_engine)
    tables = set(insp.get_table_names())

    # All 10 domain tables exist (alembic_version is created by Alembic itself).
    missing = EXPECTED_TABLES - tables
    assert not missing, f"baseline upgrade did not create: {sorted(missing)}"

    # pgvector extension was installed by the migration.
    with sync_engine.connect() as conn:
        ext = conn.execute(
            text("select extversion from pg_extension where extname='vector'")
        ).scalar()
    assert ext is not None


@pytest.mark.asyncio
async def test_alembic_baseline_matches_models():
    # After upgrading to head, autogenerate must produce NO operations — i.e. the
    # baseline migration is in sync with the ORM models.
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.database import Base
    import app.models  # noqa: F401 — ensure all models are registered on Base.metadata

    _reset_public_schema()
    command.upgrade(_alembic_config(), "head")

    sync_engine = create_engine(settings.database_url_sync, future=True)
    with sync_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diff = compare_metadata(ctx, Base.metadata)

    # The pgvector HNSW index is created in the baseline migration via raw SQL
    # (op.execute) and is intentionally NOT declared on the ORM model, so
    # autogenerate always wants to "remove" it. Ignore that known, deliberate diff.
    def _is_hnsw(op):
        try:
            return getattr(op[1], "name", None) == "ix_articles_embedding_hnsw"
        except (IndexError, TypeError):
            return False

    drift = [op for op in diff if not _is_hnsw(op)]
    assert drift == [], f"models drifted from baseline migration: {drift}"
