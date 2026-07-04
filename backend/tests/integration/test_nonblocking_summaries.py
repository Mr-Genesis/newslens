"""Non-blocking summaries: /clusters/{id} and /briefing return a snippet fallback INSTANTLY for a
cluster with no summary yet, schedule the real LLM summary in the background, and never persist the
snippet (so backfill_summaries still generates the real one)."""
import pytest

from app.models import Article, ClusterArticle, EmbeddingStatus, Source, SourceType, StoryCluster

SNIPPET = "First sentence here. Second sentence here. Third one."
EXPECTED = "First sentence here. Second sentence here."


async def _cluster_without_summary(db_session, n_articles: int = 1):
    src = Source(name=f"NB{id(object())}", url=f"https://x.example/nb-{id(object())}", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    cl = StoryCluster(title="Story", summary=None)  # no summary yet
    db_session.add(cl)
    await db_session.flush()
    for i in range(n_articles):
        art = Article(
            title=f"T{i}", url=f"https://x.example/nb-a-{cl.id}-{i}", source_id=src.id,
            snippet=SNIPPET, embedding_status=EmbeddingStatus.complete,
        )
        db_session.add(art)
        await db_session.flush()
        db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()
    return cl


@pytest.mark.asyncio
async def test_get_cluster_returns_snippet_fallback_and_schedules_without_persisting(
    aclient, db_session, monkeypatch
):
    from app.services import summarizer

    scheduled: list[int] = []
    monkeypatch.setattr(summarizer, "schedule_summary", lambda cid: scheduled.append(cid))

    cl = await _cluster_without_summary(db_session)

    resp = await aclient.get(f"/clusters/{cl.id}")
    assert resp.status_code == 200
    assert resp.json()["summary"] == EXPECTED  # instant snippet fallback, not blocked on the LLM
    assert scheduled == [cl.id]  # real summary warmed in the background

    await db_session.refresh(cl)
    assert cl.summary is None  # snippet was NOT persisted — backfill must still generate the real one


@pytest.mark.asyncio
async def test_briefing_returns_snippet_fallback_and_schedules(aclient, db_session, monkeypatch):
    from app.services import summarizer

    scheduled: list[int] = []
    monkeypatch.setattr(summarizer, "schedule_summary", lambda cid: scheduled.append(cid))

    cl = await _cluster_without_summary(db_session, n_articles=2)  # multi-source → "settled"

    resp = await aclient.get("/briefing")
    assert resp.status_code == 200
    story = next((s for s in resp.json()["stories"] if s.get("cluster_id") == cl.id), None)
    assert story is not None, "the no-summary cluster should still appear in the briefing"
    assert story["summary"] == EXPECTED  # snippet fallback, not a blocking LLM call
    assert cl.id in scheduled

    await db_session.refresh(cl)
    assert cl.summary is None  # not persisted
