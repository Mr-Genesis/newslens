"""WS-5 (#115): the entity co-occurrence graph — a nightly, decayed aggregation of which entities
share story clusters, and the one-hop candidate lookup that feeds interest expansion.

The nightly job REBUILDS `entity_edges` from scratch each run (a derived cache): edge weight =
Σ over the clusters two entities share of exp(-ln2·cluster_age/half_life). Because the weight is a
pure function of the current article_entities + cluster state, the job is idempotent AND skip-tolerant
— a missed night just means staler weights, and the next run recomputes correctly. Only the top-K
edges per source (by weight) are kept.

    article_entities × cluster_article ─▶ (cluster, entity) ─▶ self-join on cluster ─▶ decayed pair sum
                                                                        │
                                                        top-K per src ─▶ replace entity_edges (txn)
"""
import structlog
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import Article, ArticleEntity, ClusterArticle, EntityEdge

logger = structlog.get_logger()

_LN2 = 0.6931471805599453


def _rank_edges(pairs: list[tuple[int, int, float]], k: int) -> dict[tuple[int, int], float]:
    """Pure: expand unordered (src<dst) weighted pairs into BOTH directions and keep the top-K
    neighbours per source by weight. Deterministic tie-break by (weight, dst) so repeated runs and
    the idempotency test are stable."""
    by_src: dict[int, list[tuple[int, float]]] = {}
    for src, dst, w in pairs:
        by_src.setdefault(src, []).append((dst, w))
        by_src.setdefault(dst, []).append((src, w))
    edges: dict[tuple[int, int], float] = {}
    for src, neighbours in by_src.items():
        for dst, w in sorted(neighbours, key=lambda x: (x[1], x[0]), reverse=True)[:k]:
            edges[(src, dst)] = w
    return edges


async def _cooccurrence_weights(db: AsyncSession) -> list[tuple[int, int, float]]:
    """Unordered entity pairs (src<dst) with Σ of per-shared-cluster exponential decay. Cluster age =
    now − the cluster's newest article published_at (clusters with no dated article are skipped)."""
    ts = (
        select(ClusterArticle.cluster_id.label("cid"), func.max(Article.published_at).label("ts"))
        .join(Article, Article.id == ClusterArticle.article_id)
        .where(Article.published_at.isnot(None))
        .group_by(ClusterArticle.cluster_id)
        .subquery()
    )
    ce = (
        select(ClusterArticle.cluster_id.label("cid"), ArticleEntity.entity_id.label("eid"))
        .join(ArticleEntity, ArticleEntity.article_id == ClusterArticle.article_id)
        .distinct()
        .subquery()
    )
    ce1, ce2 = ce.alias("ce1"), ce.alias("ce2")
    age_days = func.greatest(0.0, func.extract("epoch", func.now() - ts.c.ts) / 86400.0)
    decay = func.exp(-_LN2 * age_days / settings.entity_edge_half_life_days)
    q = (
        select(ce1.c.eid.label("src"), ce2.c.eid.label("dst"), func.sum(decay).label("weight"))
        .select_from(ce1)
        .join(ce2, ce1.c.cid == ce2.c.cid)
        .join(ts, ts.c.cid == ce1.c.cid)
        .where(ce1.c.eid < ce2.c.eid)
        .group_by(ce1.c.eid, ce2.c.eid)
    )
    return [(int(s), int(d), float(w)) for s, d, w in (await db.execute(q)).all()]


async def _replace_edges(db: AsyncSession, edges: dict[tuple[int, int], float]) -> None:
    """Atomically swap the whole derived table: delete all, then bulk-insert. Transactional, so a
    concurrent reader sees the old set or the new set, never an empty table — and the result is
    identical for identical input (idempotent)."""
    await db.execute(delete(EntityEdge))
    if edges:
        await db.execute(
            insert(EntityEdge),
            [{"src_entity_id": s, "dst_entity_id": d, "weight": w} for (s, d), w in edges.items()],
        )


async def _rebuild(db: AsyncSession) -> dict[str, int]:
    pairs = await _cooccurrence_weights(db)
    edges = _rank_edges(pairs, settings.entity_edge_top_k)
    await _replace_edges(db, edges)
    return {"pairs": len(pairs), "edges": len(edges)}


async def aggregate_entity_edges(db: AsyncSession | None = None) -> None:
    """APScheduler nightly job: rebuild entity_edges from the current co-occurrence state. No-op when
    disabled. Idempotent + skip-tolerant (full recompute), so a missed night never corrupts weights.
    Opens its own session + commits when called by the scheduler (db=None); accepts an injected
    session (tests) whose transaction the caller owns."""
    if not settings.entity_edge_enabled:
        return
    if db is None:
        async with async_session() as own:
            stats = await _rebuild(own)
            await own.commit()
    else:
        stats = await _rebuild(db)  # caller owns the transaction
    logger.info("entity_edges_aggregated", **stats)


async def one_hop_candidates(
    db: AsyncSession, seed_weights: dict[int, float]
) -> dict[int, float]:
    """Adjacent-interest scores: for the user's seed entities (entity_id → affinity), sum
    edge_weight × affinity over their graph neighbours. Returns {neighbour_entity_id: score}. Empty
    when there are no seeds — the no-op path for a zero-signal user."""
    if not seed_weights:
        return {}
    rows = (
        await db.execute(
            select(EntityEdge.src_entity_id, EntityEdge.dst_entity_id, EntityEdge.weight).where(
                EntityEdge.src_entity_id.in_(sorted(seed_weights))
            )
        )
    ).all()
    out: dict[int, float] = {}
    for src, dst, w in rows:
        out[dst] = out.get(dst, 0.0) + float(w) * seed_weights[src]
    return out
