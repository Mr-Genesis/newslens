"""E0: /feed must report real source_count + cluster_id and, per Phase 4
(docs/fixes/follow-rails-identical-rootcause.md), COLLAPSE same-cluster articles to one row (so a
multi-source story is one row with an N-sources badge, not N near-identical rows), while still serving
the feed with a bounded query count (no per-article N+1)."""
import pytest
from sqlalchemy import event

from app.models import (
    Article,
    ClusterArticle,
    EmbeddingStatus,
    Source,
    SourceType,
    StoryCluster,
    User,
)


async def _seed(db_session):
    src = Source(name="Src", url="https://x.example/feed-src", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    arts = []
    for i in range(3):
        a = Article(
            title=f"Clustered {i}", url=f"https://x.example/c{i}",
            source_id=src.id, embedding_status=EmbeddingStatus.complete,
        )
        db_session.add(a)
        arts.append(a)
    standalone = Article(
        title="Standalone", url="https://x.example/solo",
        source_id=src.id, embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(standalone)
    cl = StoryCluster(title="Big story", summary="A real summary exists")
    db_session.add(cl)
    await db_session.flush()
    for a in arts:
        db_session.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db_session.flush()
    return cl, arts, standalone


@pytest.mark.asyncio
async def test_feed_collapses_cluster_and_reports_source_count(aclient, db_session):
    cl, _arts, _standalone = await _seed(db_session)
    resp = await aclient.get("/feed?per_page=50")
    assert resp.status_code == 200
    items = resp.json()["articles"]

    # Phase 4: the 3 clustered articles collapse to ONE representative row (which of the three wins is
    # order-dependent and not asserted), so the feed shows exactly two stories — the cluster + the
    # standalone — not four article rows. The badge still reflects the true cluster size.
    clustered = [it for it in items if it["cluster_id"] == cl.id]
    assert len(clustered) == 1, f"cluster should collapse to one row, got {len(clustered)}"
    rep = clustered[0]
    assert rep["source_count"] == 3
    assert rep["has_ai_summary"] is True
    assert rep["title"] in {"Clustered 0", "Clustered 1", "Clustered 2"}

    standalone = [it for it in items if it["title"] == "Standalone"]
    assert len(standalone) == 1
    assert standalone[0]["source_count"] == 1
    assert standalone[0]["cluster_id"] is None
    assert standalone[0]["has_ai_summary"] is False

    assert len(items) == 2  # one row per cluster + the standalone


@pytest.mark.asyncio
async def test_feed_no_n_plus_one(aclient, db_session, engine):
    """The feed resolves cluster membership + source counts in aggregate, so the number
    of SQL round-trips must NOT grow per article. Count statements via an event listener
    and assert a small constant bound regardless of how many articles are returned."""
    # Seed many standalone articles plus one multi-source cluster.
    src = Source(name="NSrc", url="https://n.example/src", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    cl = StoryCluster(title="Cluster", summary="s")
    db_session.add(cl)
    await db_session.flush()
    for i in range(25):
        a = Article(
            title=f"Item {i}", url=f"https://n.example/{i}",
            source_id=src.id, embedding_status=EmbeddingStatus.complete,
        )
        db_session.add(a)
        await db_session.flush()
        if i < 4:  # first few share a cluster
            db_session.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db_session.flush()

    counter = {"n": 0}

    def _before_cursor(conn, cursor, statement, parameters, context, executemany):
        # Only count real SELECTs the endpoint issues (ignore SAVEPOINT/RELEASE/BEGIN).
        s = statement.lstrip().upper()
        if s.startswith("SELECT"):
            counter["n"] += 1

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _before_cursor)
    try:
        resp = await aclient.get("/feed?per_page=50")
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before_cursor)

    assert resp.status_code == 200
    # Phase 4: the 4 clustered articles collapse to one row → 21 standalone + 1 cluster rep = 22.
    assert len(resp.json()["articles"]) == 22
    # Endpoint issues a bounded set of queries: count, page, source selectin,
    # cluster-membership, per-cluster count, summary set, recent feedback, and WS-5's one-hop seed
    # probe (a single O(1) UER lookup — 0 rows for this zero-signal user, then expansion short-circuits).
    # Collapse is pure Python (adds no SELECTs). Far fewer than 1-per-article. Allow generous headroom.
    assert counter["n"] <= 13, f"feed issued {counter['n']} SELECTs (possible N+1)"


@pytest.mark.asyncio
async def test_cluster_response_includes_coherence(aclient, db_session):
    """GET /clusters/{id} surfaces the real persisted coherence value."""
    # The default user must exist — get_cluster records a read against DEFAULT_USER_ID.
    if await db_session.get(User, 1) is None:
        db_session.add(User(id=1))
        await db_session.flush()
    src = Source(name="CSrc", url="https://c.example/src", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    a = Article(
        title="Cohesive story", snippet="detail", url="https://c.example/a",
        source_id=src.id, embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(a)
    cl = StoryCluster(title="Cluster", summary="real summary", coherence=0.87)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db_session.flush()

    resp = await aclient.get(f"/clusters/{cl.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == cl.id
    assert body["coherence"] == pytest.approx(0.87)
