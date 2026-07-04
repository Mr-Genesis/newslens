"""Free-tier Gemini embeddings are ~1,000 req/DAY. The backfill must (1) batch many articles into
ONE request and (2) back off on a 429 instead of re-firing a dead quota every 5 min (the death
spiral that produced 1,709 429s in a day). TDD.
"""
import time

import pytest
from sqlalchemy import func, select

from app.models import Article, EmbeddingStatus, Source, SourceType
from app.services import embeddings


async def _pending_articles(db, n):
    s = Source(name="w", url="https://w.ex", rss_url="https://w.ex/r",
               source_type=SourceType.wire, region="global", category="world")
    db.add(s)
    await db.flush()
    for i in range(n):
        db.add(Article(title=f"t{i}", snippet="a long enough snippet body for the card here",
                       url=f"https://w.ex/{i}", source_id=s.id,
                       embedding_status=EmbeddingStatus.pending))
    await db.flush()
    return s


async def _count(db, status):
    return (await db.execute(
        select(func.count()).select_from(Article).where(Article.embedding_status == status)
    )).scalar_one()


@pytest.mark.asyncio
async def test_backfill_embeds_all_in_ONE_batched_request(db_session, monkeypatch):
    await _pending_articles(db_session, 5)
    calls = {"n": 0, "count": 0}

    async def _fake_batch(texts):
        calls["n"] += 1
        calls["count"] = len(texts)
        return [[0.1] * 768 for _ in texts]

    async def _key():
        return "k"

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _key)
    monkeypatch.setattr(embeddings, "generate_embeddings_batch", _fake_batch)
    embeddings._embedding_backoff_until = 0.0

    await embeddings.backfill_embeddings(session=db_session)

    assert calls["n"] == 1        # ONE API request for all 5 articles, not 5
    assert calls["count"] == 5
    assert await _count(db_session, EmbeddingStatus.complete) >= 5


@pytest.mark.asyncio
async def test_backfill_backs_off_on_quota_and_skips_the_next_run(db_session, monkeypatch):
    await _pending_articles(db_session, 3)
    calls = {"n": 0}

    async def _boom(texts):
        calls["n"] += 1
        raise embeddings.QuotaExceeded("429 Resource has been exhausted")

    async def _key():
        return "k"

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _key)
    monkeypatch.setattr(embeddings, "generate_embeddings_batch", _boom)
    embeddings._embedding_backoff_until = 0.0

    await embeddings.backfill_embeddings(session=db_session)   # hits 429 → set cooldown
    assert calls["n"] == 1
    assert embeddings._embedding_backoff_until > time.time()   # cooldown armed
    # articles NOT force-failed on a quota miss (it wasn't their fault) — they retry after cooldown
    assert await _count(db_session, EmbeddingStatus.pending) == 3

    await embeddings.backfill_embeddings(session=db_session)   # within cooldown → skip entirely
    assert calls["n"] == 1                                     # the API was NOT hit again

    embeddings._embedding_backoff_until = 0.0                  # cleanup for other tests


@pytest.mark.asyncio
async def test_non_quota_batch_failure_falls_back_to_per_text_isolating_a_poison(db_session, monkeypatch):
    """A batch fails atomically, so one poison text could otherwise starve the rest forever. On a
    non-quota batch failure the backfill retries each text individually — good ones still embed,
    only the offender stays failed. The pipeline is NOT stalled."""
    await _pending_articles(db_session, 3)  # titles t0, t1, t2
    calls = {"single": 0}

    async def _batch_none(texts):
        return None  # non-quota whole-batch failure

    async def _single(text, **kwargs):
        calls["single"] += 1
        return None if "t1 " in text else [0.5] * 768  # t1 is the poison

    async def _key():
        return "k"

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _key)
    monkeypatch.setattr(embeddings, "generate_embeddings_batch", _batch_none)
    monkeypatch.setattr(embeddings, "generate_embedding", _single)
    embeddings._embedding_backoff_until = 0.0

    await embeddings.backfill_embeddings(session=db_session)

    assert calls["single"] == 3
    assert await _count(db_session, EmbeddingStatus.complete) == 2  # the other two are unblocked
    assert await _count(db_session, EmbeddingStatus.failed) == 1    # only the poison stays failed
    embeddings._embedding_backoff_until = 0.0


@pytest.mark.asyncio
async def test_systemic_non_quota_failure_arms_a_short_backoff(db_session, monkeypatch):
    """If even the per-text fallback embeds nothing (transport/systemic), back off instead of
    re-firing the identical failing work every 5 minutes."""
    await _pending_articles(db_session, 2)

    async def _batch_none(texts):
        return None

    async def _single_none(text, **kwargs):
        return None

    async def _key():
        return "k"

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _key)
    monkeypatch.setattr(embeddings, "generate_embeddings_batch", _batch_none)
    monkeypatch.setattr(embeddings, "generate_embedding", _single_none)
    embeddings._embedding_backoff_until = 0.0

    await embeddings.backfill_embeddings(session=db_session)
    assert embeddings._embedding_backoff_until > time.time()  # short backoff armed
    embeddings._embedding_backoff_until = 0.0


@pytest.mark.asyncio
async def test_generate_embeddings_batch_raises_quota_on_429(monkeypatch):
    async def _key():
        return "k"

    def _boom(*a, **k):
        raise RuntimeError("429 Resource has been exhausted (quota)")

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _key)
    monkeypatch.setattr(embeddings, "_embed_batch_sync", _boom)

    with pytest.raises(embeddings.QuotaExceeded):
        await embeddings.generate_embeddings_batch(["a", "b"])
    assert embeddings.last_embedding_error()["category"] == "quota"


@pytest.mark.asyncio
async def test_generate_embeddings_batch_returns_vectors_and_clears_error(monkeypatch):
    async def _key():
        return "k"

    def _ok(key, model, texts, task_type, output_dim):
        return [[0.1, 0.2], [0.3, 0.4]]

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _key)
    monkeypatch.setattr(embeddings, "_embed_batch_sync", _ok)
    embeddings._last_embedding_error = {"category": "quota", "message": "old", "when": "x"}

    out = await embeddings.generate_embeddings_batch(["a", "b"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]
    assert embeddings.last_embedding_error() is None
