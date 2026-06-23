"""E5/E6/E7/E8: cluster lens endpoints — generate + cache + graceful unavailable."""
import pytest

from app.models import (
    Article,
    ClusterArticle,
    EmbeddingStatus,
    Source,
    SourceType,
    StoryCluster,
)


async def _seed_cluster(db_session, n=2):
    src = Source(name="S", url="https://l.example/src", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    arts = []
    for i in range(n):
        a = Article(
            title=f"Story {i}", snippet="detail text", url=f"https://l.example/{i}",
            source_id=src.id, embedding_status=EmbeddingStatus.complete,
        )
        db_session.add(a)
        arts.append(a)
    cl = StoryCluster(title="Cluster", summary="s")
    db_session.add(cl)
    await db_session.flush()
    for a in arts:
        db_session.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db_session.flush()
    return cl


@pytest.mark.asyncio
async def test_impact_generates_then_serves_from_cache(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    r1 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r1.status_code == 200
    assert r1.json().get("cached") is False
    assert fake_llm["generate"] == 1
    r2 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r2.json().get("cached") is True
    assert fake_llm["generate"] == 1  # cache hit, no second LLM call


@pytest.mark.asyncio
async def test_analysis_keyfacts_and_5ws_generate(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/analysis?lens=key_facts")).status_code == 200
    assert (await aclient.get(f"/clusters/{cl.id}/analysis?lens=5ws")).status_code == 200
    assert fake_llm["generate"] == 2  # two distinct sub-lenses


@pytest.mark.asyncio
async def test_analysis_invalid_lens_400(aclient, db_session):
    cl = await _seed_cluster(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/analysis?lens=bogus")).status_code == 400


@pytest.mark.asyncio
async def test_strategic_and_trivia(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/strategic")).status_code == 200
    assert (await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=hard")).status_code == 200
    assert (await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=bogus")).status_code == 400


@pytest.mark.asyncio
async def test_impact_graceful_when_llm_fails(aclient, db_session):
    # No fake_llm -> real seam. Whether the key is missing or the API errors
    # (e.g. quota), the lens must return a typed unavailable, never a 500.
    cl = await _seed_cluster(db_session)
    r = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r.status_code == 200
    assert r.json().get("unavailable") is True
