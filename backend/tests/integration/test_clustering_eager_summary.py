"""Eager summaries: run_clustering schedules a background summary the moment a NEW cluster forms, so
it's warm before any user opens it (turns the read-path on-demand into a rare cold path)."""
import contextlib

import pytest

from app.models import Article, EmbeddingStatus, Source, SourceType


@pytest.mark.asyncio
async def test_run_clustering_eagerly_schedules_summary_for_a_new_cluster(db_session, monkeypatch):
    from app.services import clustering, summarizer

    # Route the job's own async_session() to the test's (uncommitted) transaction.
    @contextlib.asynccontextmanager
    async def _fake():
        yield db_session

    monkeypatch.setattr(clustering, "async_session", _fake)

    # Force the new-cluster path (no nearest match) and capture the eager schedule.
    async def _no_match(_article):
        return None

    monkeypatch.setattr(clustering, "_find_nearest_cluster", _no_match)
    scheduled: list[int] = []
    monkeypatch.setattr(summarizer, "schedule_summary", lambda cid: scheduled.append(cid))

    src = Source(name="ECL", url="https://x.example/ecl", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    art = Article(
        title="Fresh cluster seed", url="https://x.example/ecl-a", source_id=src.id,
        embedding_status=EmbeddingStatus.complete, embedding=[0.1] * 768,
    )
    db_session.add(art)
    await db_session.flush()

    await clustering.run_clustering()

    assert len(scheduled) == 1  # the newly-created cluster was scheduled for a background summary
