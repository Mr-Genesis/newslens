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

    def _schema_shape(prompt: str) -> dict:
        """Return realistic lens-shaped JSON keyed off cues in the prompt.

        The real prompt builders (see app/services/lenses.py) embed distinctive
        instructions per lens; we sniff those so tests see the true response shape
        rather than an opaque ``{"stub": true}``.
        """
        p = (prompt or "").lower()
        # E7 strategic / game-theory
        if "game-theory" in p or "game type" in p or '"game_type"' in p:
            return {
                "actors": [
                    {
                        "name": "Country A",
                        "incentive": "secure borders",
                        "likely_move": "escalate pressure",
                    },
                    {
                        "name": "Country B",
                        "incentive": "preserve status quo",
                        "likely_move": "seek allies",
                    },
                ],
                "game_type": "chicken",
                "second_order": [
                    "regional alignment shifts",
                    "commodity price volatility",
                ],
                "non_obvious_take": "the loud threats are a bargaining posture, not intent",
            }
        # E6 WIIFM impact
        if '"dimensions"' in p or "what's in it for me" in p:
            return {
                "headline": "Modest near-term effect; worth monitoring",
                "dimensions": [
                    {"key": "finance", "label": "Finance", "body": "Rates may tick up."},
                    {"key": "profession", "label": "Your field", "body": "Demand steady."},
                    {"key": "policy", "label": "Policy", "body": "New rules expected."},
                    {"key": "daily", "label": "Daily life", "body": "Prices stable."},
                ],
            }
        # E8 trivia / quiz
        if "multiple-choice" in p or '"answer_index"' in p or "quiz" in p:
            return {
                "questions": [
                    {
                        "question": "What is the main event?",
                        "options": ["a", "b", "c", "d"],
                        "answer_index": 1,
                        "explanation": "Because b is described in the coverage.",
                    },
                    {
                        "question": "Who is involved?",
                        "options": ["w", "x", "y", "z"],
                        "answer_index": 0,
                        "explanation": "w is named as the key actor.",
                    },
                    {
                        "question": "When did it happen?",
                        "options": ["1", "2", "3", "4"],
                        "answer_index": 2,
                        "explanation": "The third option matches the reported date.",
                    },
                ]
            }
        # E5 analysis: key_facts
        if '"facts"' in p or "concrete facts" in p:
            return {"facts": ["First key fact.", "Second key fact.", "Third key fact."]}
        # E5 analysis: 5 Ws
        if "five ws" in p or ('"who"' in p and '"why"' in p):
            return {
                "who": "Key parties",
                "what": "An agreement was reached",
                "when": "This week",
                "where": "Geneva",
                "why": "To de-escalate tensions",
            }
        # E5 analysis: profession lens
        if '"points"' in p or "means specifically for" in p:
            return {
                "headline": "Here's the one-line takeaway for you",
                "points": ["Point one.", "Point two.", "Point three."],
            }
        return {"result": "generic"}

    async def _gen(prompt, *, system=None, schema=None, model=None):
        calls["generate"] += 1
        if schema is None:
            return "STUB SUMMARY"
        return _schema_shape(prompt)

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
