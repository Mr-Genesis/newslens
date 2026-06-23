"""Integration test harness (E★) — runs against a real Postgres + pgvector.

MUST RUN IN DOCKER (greenlet's async DLL fails on native Windows-ARM):

    docker compose run --rm \
      -e DATABASE_URL=postgresql+asyncpg://newslens:newslens_dev@db:5432/newslens_test \
      backend python -m pytest tests/integration -q

Per-test isolation uses an outer transaction + ``join_transaction_mode="create_savepoint"``
so endpoint ``commit()`` calls are contained and rolled back after each test.
"""
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.database import Base, get_db
from app.main import app

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://newslens:newslens_dev@db:5432/newslens_test",
    ),
)


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DB_URL, future=True)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_articles_embedding_hnsw "
                "ON articles USING hnsw (embedding vector_cosine_ops)"
            )
        )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


@pytest_asyncio.fixture
async def aclient(db_session):
    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def fake_llm(monkeypatch):
    """Patch the generation + embedding seams to deterministic values (no network)."""
    calls = {"generate": 0, "embed": 0}

    async def _gen(prompt, *, system=None, schema=None, model=None):
        calls["generate"] += 1
        return {"stub": True} if schema is not None else "STUB SUMMARY"

    async def _embed(_text):
        calls["embed"] += 1
        from app.config import settings as _s
        v = [0.0] * _s.embedding_dimensions
        v[0] = 1.0
        return v

    import app.services.embeddings as emb
    import app.services.llm as llm
    monkeypatch.setattr(llm, "generate", _gen)
    monkeypatch.setattr(emb, "generate_embedding", _embed)
    return calls
