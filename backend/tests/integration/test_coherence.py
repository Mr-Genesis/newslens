"""S4: cluster_coherence — real consensus agreement ratio when cached, else honest fallback."""
import pytest
from sqlalchemy import select  # noqa: F401 (kept for parity with sibling test modules)

from app.models import (
    Article, ClusterArticle, EmbeddingStatus, Source, SourceType, StoryCluster,
)
from app.services import lenses

_n = 0


async def _cluster(db, n_sources, *, stored_coherence=None):
    """A cluster of n_sources distinct-source articles (summary set → no on-demand LLM call)."""
    global _n
    cl = StoryCluster(title="C", summary="s", coherence=stored_coherence)
    db.add(cl)
    await db.flush()
    arts = []
    for _i in range(n_sources):
        _n += 1
        s = Source(name=f"S{_n}", url=f"https://coh/{_n}", source_type=SourceType.wire)
        db.add(s)
        await db.flush()
        a = Article(title=f"A{_n}", url=f"https://coh/{_n}/a", source_id=s.id,
                    embedding_status=EmbeddingStatus.complete)
        db.add(a)
        await db.flush()
        db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
        arts.append(a)
    await db.flush()
    return cl, arts


async def _cache_consensus(db, cl, arts, agree, total):
    sh = lenses._source_hash(arts)
    await lenses._cache_write(db, cl, "extra_json", "consensus", sh,
                              {"agree_count": agree, "total": total, "dissent": [], "summary": "x"})
    await db.refresh(cl, ["extra_json"])


@pytest.mark.asyncio
async def test_coherence_uses_cached_consensus(db_session):
    cl, arts = await _cluster(db_session, 4)  # source-overlap heuristic would be 0.85
    await _cache_consensus(db_session, cl, arts, agree=1, total=4)
    assert lenses.cluster_coherence(cl, arts) == pytest.approx(0.25)  # real 1/4, not the 0.85 heuristic


@pytest.mark.asyncio
async def test_coherence_contested_scores_below_heuristic_floor(db_session):
    cl, arts = await _cluster(db_session, 5)  # heuristic would be 0.95
    await _cache_consensus(db_session, cl, arts, agree=2, total=5)
    assert lenses.cluster_coherence(cl, arts) == pytest.approx(0.4)  # honest: contested → below floor


@pytest.mark.asyncio
async def test_coherence_falls_back_to_heuristic(db_session):
    cl, arts = await _cluster(db_session, 4)  # no consensus, no stored value
    assert lenses.cluster_coherence(cl, arts) == pytest.approx(0.85)  # >=3 distinct sources


@pytest.mark.asyncio
async def test_coherence_prefers_stored_when_no_consensus(db_session):
    cl, arts = await _cluster(db_session, 2, stored_coherence=0.5)
    assert lenses.cluster_coherence(cl, arts) == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_get_cluster_surfaces_consensus_coherence(aclient, db_session):
    cl, arts = await _cluster(db_session, 4)
    await _cache_consensus(db_session, cl, arts, agree=3, total=4)
    body = (await aclient.get(f"/clusters/{cl.id}")).json()
    assert body["coherence"] == pytest.approx(0.75)  # 3/4 from the real consensus, end-to-end
