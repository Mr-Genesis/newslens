"""E4 integration: hybrid search — keyword ranks above semantic-only, the HNSW index
exists after migration, results are grouped/deduped by cluster, and repeated queries
reuse one cached query embedding."""
import pytest
from sqlalchemy import text

from app.config import settings
from app.models import (
    Article,
    ClusterArticle,
    EmbeddingStatus,
    Source,
    SourceType,
    StoryCluster,
)


async def _article(db_session, src, title, url, embedding):
    a = Article(
        title=title, url=url, source_id=src.id, embedding=embedding,
        embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(a)
    await db_session.flush()
    return a


@pytest.mark.asyncio
async def test_keyword_ranks_above_semantic_only(aclient, db_session, fake_llm):
    src = Source(name="S", url="https://s.example/se", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    dim = settings.embedding_dimensions
    near = [0.0] * dim
    near[0] = 1.0  # matches fake query embedding [1,0,...]
    far = [0.0] * dim
    far[1] = 1.0
    await _article(db_session, src, "Reliance earnings beat estimates", "https://s.example/kw", far)
    await _article(db_session, src, "Tata quarterly report", "https://s.example/sem", near)

    r = await aclient.get("/search?q=Reliance")
    assert r.status_code == 200
    titles = [x["title"] for x in r.json()["results"]]
    assert "Reliance earnings beat estimates" in titles
    assert titles.index("Reliance earnings beat estimates") < titles.index("Tata quarterly report")


@pytest.mark.asyncio
async def test_search_empty_query_rejected(aclient, db_session):
    r = await aclient.get("/search?q=")
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_hnsw_index_exists_after_migration(db_session):
    """The semantic-search HNSW index must be present (created by the baseline migration /
    the integration harness mirror of it). Without it, NN search degrades to a seq scan."""
    row = (
        await db_session.execute(
            text("SELECT indexname FROM pg_indexes WHERE indexname = :n"),
            {"n": "ix_articles_embedding_hnsw"},
        )
    ).scalar_one_or_none()
    assert row == "ix_articles_embedding_hnsw"


@pytest.mark.asyncio
async def test_search_groups_by_cluster_dedup_articles(aclient, db_session, fake_llm):
    """When a query matches multiple articles in the same cluster, the result set
    collapses to one row per cluster (dedup). Two clusters -> exactly two results."""
    src = Source(name="S", url="https://g.example/se", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    dim = settings.embedding_dimensions
    vec = [0.0] * dim
    vec[0] = 1.0

    # Cluster A: two articles both matching the keyword "Mandate".
    a1 = await _article(db_session, src, "Mandate ruling lands", "https://g.example/a1", vec)
    a2 = await _article(db_session, src, "Mandate reaction grows", "https://g.example/a2", vec)
    cl_a = StoryCluster(title="Mandate A", summary="s")
    db_session.add(cl_a)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl_a.id, article_id=a1.id))
    db_session.add(ClusterArticle(cluster_id=cl_a.id, article_id=a2.id))

    # Cluster B: one article also matching "Mandate".
    b1 = await _article(db_session, src, "Mandate appeal filed", "https://g.example/b1", vec)
    cl_b = StoryCluster(title="Mandate B", summary="s")
    db_session.add(cl_b)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl_b.id, article_id=b1.id))
    await db_session.flush()

    r = await aclient.get("/search?q=Mandate")
    assert r.status_code == 200
    results = r.json()["results"]
    cluster_ids = [x["cluster_id"] for x in results]
    # Exactly one result per cluster — no duplicate cluster_ids.
    assert sorted(cluster_ids) == sorted({cl_a.id, cl_b.id})
    assert len(results) == 2


@pytest.mark.asyncio
async def test_query_embedding_cached(aclient, db_session, monkeypatch):
    """Calling /search twice with the same query embeds the query exactly once —
    the second call hits the in-process query-embedding cache."""
    import app.services.embeddings as emb

    # Reset the module-level cache so the count is deterministic across the suite.
    emb._query_embedding_cache.clear()

    calls = {"n": 0}

    async def _spy_embed(_text):
        calls["n"] += 1
        v = [0.0] * settings.embedding_dimensions
        v[0] = 1.0
        return v

    monkeypatch.setattr(emb, "generate_embedding", _spy_embed)

    src = Source(name="S", url="https://q.example/se", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    await _article(
        db_session, src, "Budget session opens", "https://q.example/a",
        [1.0] + [0.0] * (settings.embedding_dimensions - 1),
    )

    r1 = await aclient.get("/search?q=Budget")
    assert r1.status_code == 200
    r2 = await aclient.get("/search?q=Budget")
    assert r2.status_code == 200

    assert calls["n"] == 1  # query embedded once, second call served from cache
