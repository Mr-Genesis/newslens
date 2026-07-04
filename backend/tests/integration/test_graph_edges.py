"""WS-5 (#115): the nightly entity co-occurrence graph — decayed pair weights, top-K bound, both
directions, idempotency, skip-tolerance."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Article, ArticleEntity, ClusterArticle, Entity, EntityEdge, Source, SourceType, StoryCluster
from app.services import graph

UTC = timezone.utc
_n = 0


async def _entity(db, name):
    global _n
    _n += 1
    e = Entity(canonical_name=f"{name}{_n}", name_norm=f"{name}{_n}".lower(), kind="org")
    db.add(e)
    await db.flush()
    return e


async def _cluster(db, entities, when):
    global _n
    _n += 1
    src = Source(name="S", url=f"https://g/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    art = Article(title=f"a{_n}", url=f"https://g/{_n}/a", source_id=src.id, published_at=when)
    db.add(art)
    await db.flush()
    c = StoryCluster(title=f"c{_n}")
    db.add(c)
    await db.flush()
    db.add(ClusterArticle(cluster_id=c.id, article_id=art.id))
    for e in entities:
        db.add(ArticleEntity(article_id=art.id, entity_id=e.id, salience=0.5))
    await db.flush()
    return c


async def _edge_map(db):
    rows = (await db.execute(select(EntityEdge.src_entity_id, EntityEdge.dst_entity_id, EntityEdge.weight))).all()
    return {(s, d): float(w) for s, d, w in rows}


# ── pure _rank_edges ──────────────────────────────────────────────────────────────────
def test_rank_edges_bounds_per_source_and_stores_both_directions():
    pairs = [(1, 2, 5.0), (1, 3, 3.0), (1, 4, 1.0)]  # entity 1 has three neighbours
    edges = graph._rank_edges(pairs, k=2)
    assert (1, 2) in edges and (1, 3) in edges          # entity 1 keeps its top-2
    assert (1, 4) not in edges                           # and drops its weakest
    assert (2, 1) in edges and (3, 1) in edges           # reverse direction stored
    assert edges[(1, 2)] == 5.0


def test_rank_edges_is_idempotent():
    pairs = [(1, 2, 5.0), (2, 3, 2.0), (1, 3, 4.0)]
    assert graph._rank_edges(pairs, 50) == graph._rank_edges(pairs, 50)


# ── the job (uses the injected test session) ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_aggregate_builds_both_direction_edges_from_a_shared_cluster(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "entity_edge_enabled", True)
    a, b, c = await _entity(db_session, "A"), await _entity(db_session, "B"), await _entity(db_session, "C")
    await _cluster(db_session, [a, b, c], datetime.now(UTC))

    await graph.aggregate_entity_edges(db_session)

    edges = await _edge_map(db_session)
    for x, y in [(a.id, b.id), (a.id, c.id), (b.id, c.id)]:
        assert (x, y) in edges and (y, x) in edges  # every co-occurring pair, both directions


@pytest.mark.asyncio
async def test_aggregate_is_idempotent_and_skip_tolerant(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "entity_edge_enabled", True)
    a, b = await _entity(db_session, "A"), await _entity(db_session, "B")
    await _cluster(db_session, [a, b], datetime.now(UTC))

    await graph.aggregate_entity_edges(db_session)
    first = await _edge_map(db_session)
    # a "skipped night" then a re-run recomputes the SAME table from scratch (no drift, no double-count)
    await graph.aggregate_entity_edges(db_session)
    assert await _edge_map(db_session) == first


@pytest.mark.asyncio
async def test_recent_cooccurrence_outweighs_old(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "entity_edge_enabled", True)
    monkeypatch.setattr(s, "entity_edge_half_life_days", 30.0)
    a, b = await _entity(db_session, "A"), await _entity(db_session, "B")
    c, d = await _entity(db_session, "C"), await _entity(db_session, "D")
    now = datetime.now(UTC)
    await _cluster(db_session, [a, b], now)                       # fresh co-occurrence
    await _cluster(db_session, [c, d], now - timedelta(days=120))  # old co-occurrence

    await graph.aggregate_entity_edges(db_session)
    edges = await _edge_map(db_session)
    assert edges[(a.id, b.id)] > edges[(c.id, d.id)]  # decay makes the fresh pair heavier


@pytest.mark.asyncio
async def test_top_k_bounds_edges_per_source(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "entity_edge_enabled", True)
    monkeypatch.setattr(s, "entity_edge_top_k", 2)
    hub = await _entity(db_session, "HUB")
    others = [await _entity(db_session, f"N{i}") for i in range(4)]
    now = datetime.now(UTC)
    # hub co-occurs with 4 others across clusters of increasing recency (so weights differ)
    for i, o in enumerate(others):
        await _cluster(db_session, [hub, o], now - timedelta(days=i))

    await graph.aggregate_entity_edges(db_session)
    edges = await _edge_map(db_session)
    hub_edges = [d for (srcid, d) in edges if srcid == hub.id]
    assert len(hub_edges) == 2  # bounded to top_k


@pytest.mark.asyncio
async def test_disabled_is_a_noop(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "entity_edge_enabled", False)
    a, b = await _entity(db_session, "A"), await _entity(db_session, "B")
    await _cluster(db_session, [a, b], datetime.now(UTC))
    await graph.aggregate_entity_edges(db_session)
    assert await _edge_map(db_session) == {}
