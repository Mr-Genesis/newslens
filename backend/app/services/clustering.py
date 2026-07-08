"""Story clustering service using pgvector nearest-neighbor search.

Groups articles about the same event into clusters.
Uses pgvector's <=> cosine distance operator for O(n) lookups instead of
O(n^2) pairwise comparison in Python.
"""

import structlog
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import (
    Article,
    ArticleEntity,
    ArticleTopic,
    ClusterArticle,
    ClusterEdge,
    EmbeddingStatus,
    StoryCluster,
)
from app.services.embeddings import vector_literal

logger = structlog.get_logger()


async def run_clustering():
    """Cluster new articles into story groups. Called by APScheduler."""
    async with async_session() as session:
        # Find articles with embeddings that aren't in any cluster yet
        result = await session.execute(
            select(Article)
            .outerjoin(ClusterArticle)
            .where(
                Article.embedding_status == EmbeddingStatus.complete,
                ClusterArticle.id.is_(None),
            )
            .order_by(Article.fetched_at.desc())
            .limit(100)
        )
        unclustered = result.scalars().all()

    if not unclustered:
        return

    new_clusters = 0
    assigned = 0

    for article in unclustered:
        if article.embedding is None:
            continue

        cluster_id = await _find_nearest_cluster(article)

        async with async_session() as session:
            if cluster_id:
                # Assign to existing cluster
                ca = ClusterArticle(
                    cluster_id=cluster_id,
                    article_id=article.id,
                )
                session.add(ca)
                await session.commit()
                assigned += 1
            else:
                # Create new cluster
                cluster = StoryCluster(title=article.title)
                session.add(cluster)
                await session.flush()

                ca = ClusterArticle(
                    cluster_id=cluster.id,
                    article_id=article.id,
                )
                session.add(ca)
                await session.commit()
                # Wave D2: link the new cluster to prior related clusters (best-effort).
                try:
                    await link_cluster(session, cluster.id)
                except Exception as e:  # noqa: BLE001 — never break clustering on edge-linking
                    logger.warning("cluster_link_failed", cluster_id=cluster.id, error=str(e))
                # Eagerly summarize the brand-new cluster in the background so it's warm before any user
                # opens it — turns the read-path on-demand into a rare cold path (deduped + gated inside).
                from app.services.summarizer import schedule_summary
                schedule_summary(cluster.id)
                new_clusters += 1

    logger.info(
        "clustering_complete",
        unclustered=len(unclustered),
        assigned_to_existing=assigned,
        new_clusters=new_clusters,
    )
    if new_clusters > 0:
        from app.services import events  # #96: signal live clients that new stories formed
        events.publish("new_cluster", {"count": new_clusters})


async def link_cluster(session: AsyncSession, cluster_id: int, max_background: int = 3) -> None:
    """Wave D2: link a cluster to prior clusters sharing a topic — nearest (by id/recency) =
    'successor', next few = 'background'. Idempotent. Powers the 'how we got here' timeline."""
    topic_ids = (
        await session.execute(
            select(ArticleTopic.topic_id)
            .join(ClusterArticle, ClusterArticle.article_id == ArticleTopic.article_id)
            .where(ClusterArticle.cluster_id == cluster_id)
        )
    ).scalars().all()
    if not topic_ids:
        return
    prior = (
        await session.execute(
            select(StoryCluster.id)
            .distinct()
            .join(ClusterArticle, ClusterArticle.cluster_id == StoryCluster.id)
            .join(ArticleTopic, ArticleTopic.article_id == ClusterArticle.article_id)
            .where(ArticleTopic.topic_id.in_(topic_ids), StoryCluster.id < cluster_id)
            .order_by(StoryCluster.id.desc())
            .limit(max_background + 1)
        )
    ).scalars().all()
    for i, prior_id in enumerate(prior):
        kind = "successor" if i == 0 else "background"
        exists = (
            await session.execute(
                select(ClusterEdge.id).where(
                    ClusterEdge.src_cluster_id == cluster_id,
                    ClusterEdge.dst_cluster_id == prior_id,
                    ClusterEdge.kind == kind,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                ClusterEdge(src_cluster_id=cluster_id, dst_cluster_id=prior_id, kind=kind)
            )
    await session.commit()


async def _find_nearest_cluster(article: Article) -> int | None:
    """Find the nearest existing cluster for an article using pgvector.

    Returns cluster_id if a similar article exists within threshold,
    or None if this should start a new cluster.
    """
    async with async_session() as session:
        # Fetch the nearest already-clustered article WITHOUT the threshold in the WHERE, then apply the
        # threshold in Python. This is behaviourally identical to filtering in SQL (the global-nearest
        # is the nearest-under-threshold iff it is itself under threshold), but it lets us LOG the
        # near-miss distance for every article — the doc↔doc distribution needed to calibrate
        # cluster_similarity_threshold from real data (mirrors rails' rail_distance_histogram). See
        # docs/fixes/follow-rails-identical-rootcause.md. The ORDER BY … LIMIT 1 rides the HNSW index.
        try:
            result = await session.execute(
                text("""
                    SELECT ca.cluster_id, a.embedding <=> :embedding AS distance
                    FROM articles a
                    JOIN cluster_articles ca ON ca.article_id = a.id
                    WHERE a.embedding IS NOT NULL
                    ORDER BY distance
                    LIMIT 1
                """),
                {"embedding": vector_literal(article.embedding)},
            )
            row = result.first()
        except Exception as e:  # noqa: BLE001 — a NN lookup failure must not abort the whole run;
            # fall back to "no match" so the article still starts its own cluster.
            logger.warning("cluster_nn_lookup_failed", article_id=getattr(article, "id", None), error=str(e))
            return None

        if not row:
            return None

        cluster_id, distance = row[0], float(row[1])
        threshold = settings.cluster_similarity_threshold
        # Near-miss = just outside the bar (threshold ≤ dist < 2×threshold): the same-event pair we are
        # most likely failing to club. A pile of these is the signal to loosen the threshold (Phase 2).
        logger.info(
            "cluster_distance_probe",
            article_id=getattr(article, "id", None),
            nearest_cluster_id=cluster_id,
            distance=round(distance, 4),
            threshold=threshold,
            matched=distance < threshold,
            near_miss=threshold <= distance < threshold * 2,
        )
        return cluster_id if distance < threshold else None

    return None


# ── Phase 3: cluster reconcile / merge ───────────────────────────────────────────────
# See docs/fixes/follow-rails-identical-rootcause.md. The strict 0.15 join bar + single-linkage +
# permanent placement can seed TWO clusters for one event that never reconcile. This job merges them.


async def _cluster_entity_sets(session: AsyncSession, cluster_ids: list[int]) -> dict[int, set[int]]:
    """cluster_id -> set of entity_ids featured in its articles (loose-band merge confirmation)."""
    rows = (
        await session.execute(
            select(ClusterArticle.cluster_id, ArticleEntity.entity_id)
            .join(ArticleEntity, ArticleEntity.article_id == ClusterArticle.article_id)
            .where(ClusterArticle.cluster_id.in_(cluster_ids))
        )
    ).all()
    out: dict[int, set[int]] = {}
    for cid, eid in rows:
        out.setdefault(cid, set()).add(eid)
    return out


async def _cluster_topic_sets(session: AsyncSession, cluster_ids: list[int]) -> dict[int, set[int]]:
    """cluster_id -> set of topic_ids on its articles. Topics are assigned at ingest, so this
    confirmation works on singletons too — unlike entities, which need a settled (≥2-source) cluster."""
    rows = (
        await session.execute(
            select(ClusterArticle.cluster_id, ArticleTopic.topic_id)
            .join(ArticleTopic, ArticleTopic.article_id == ClusterArticle.article_id)
            .where(ClusterArticle.cluster_id.in_(cluster_ids))
        )
    ).all()
    out: dict[int, set[int]] = {}
    for cid, tid in rows:
        out.setdefault(cid, set()).add(tid)
    return out


async def _merge_into(session: AsyncSession, survivor: int, losers: list[int]) -> None:
    """Fold `losers` into `survivor` in ONE transaction. FK order matters (cluster_articles and
    cluster_edges are RESTRICT): move the child cluster_articles off each loser, drop its best-effort
    timeline edges, THEN delete the emptied cluster (impressions CASCADE). No article overlap is
    possible — an article lives in exactly one cluster — so uq_cluster_article can't fire."""
    for lid in losers:
        await session.execute(
            update(ClusterArticle).where(ClusterArticle.cluster_id == lid).values(cluster_id=survivor)
        )
        # Drop edges touching the loser rather than re-point (avoids self-edge + uq_cluster_edge
        # conflicts); timeline links are best-effort and re-form on cluster creation.
        await session.execute(
            delete(ClusterEdge).where(
                or_(ClusterEdge.src_cluster_id == lid, ClusterEdge.dst_cluster_id == lid)
            )
        )
        await session.execute(delete(StoryCluster).where(StoryCluster.id == lid))
    # Survivor's article set changed → every source-set-keyed cache is stale. Clearing source_hash
    # invalidates the lens read-paths; nulling summary re-arms the snippet fallback + schedule_summary.
    await session.execute(
        update(StoryCluster)
        .where(StoryCluster.id == survivor)
        .values(
            summary=None,
            summary_generated_at=None,
            coherence=None,
            analysis_json=None,
            impact_json=None,
            strategic_json=None,
            trivia_json=None,
            extra_json=None,
            source_hash=None,
        )
    )


async def reconcile_clusters() -> None:
    """Merge same-event clusters mis-seeded as parallel singletons. Centroid-distance driven with a
    two-tier precision guard (tight pure-semantic OR loose + shared entity/topic) and union-find so a
    chain A~B~C collapses to one. Gated by cluster_merge_enabled. Idempotent + skip-tolerant: each
    group merges in its own transaction, one failure never aborts the rest, and a re-run is a no-op
    once the near-duplicates are gone. See docs/fixes/follow-rails-identical-rootcause.md."""
    if not settings.cluster_merge_enabled:
        return

    from datetime import datetime, timedelta, timezone

    import numpy as np

    async with async_session() as session:
        since = datetime.now(timezone.utc) - timedelta(hours=settings.cluster_merge_window_hours)
        cand_ids = (
            await session.execute(
                select(ClusterArticle.cluster_id)
                .join(Article, Article.id == ClusterArticle.article_id)
                .where(Article.published_at.isnot(None), Article.published_at >= since)
                .distinct()
                .limit(settings.cluster_merge_max)
            )
        ).scalars().all()
        if len(cand_ids) < 2:
            return

        rows = (
            await session.execute(
                select(ClusterArticle.cluster_id, Article.embedding)
                .join(Article, Article.id == ClusterArticle.article_id)
                .where(ClusterArticle.cluster_id.in_(cand_ids), Article.embedding.isnot(None))
            )
        ).all()
        vecs: dict[int, list] = {}
        for cid, emb in rows:
            if emb is not None:
                vecs.setdefault(cid, []).append(np.asarray(emb, dtype=float))
        ids = [c for c in cand_ids if c in vecs]
        if len(ids) < 2:
            return

        # Per-cluster L2-normalized centroid → dot product IS cosine similarity; distance = 1 - dot.
        cents = []
        for c in ids:
            m = np.mean(np.stack(vecs[c]), axis=0)
            norm = float(np.linalg.norm(m))
            cents.append(m / norm if norm > 0 else m)
        sim = np.stack(cents) @ np.stack(cents).T

        counts = dict(
            (
                await session.execute(
                    select(ClusterArticle.cluster_id, func.count())
                    .where(ClusterArticle.cluster_id.in_(ids))
                    .group_by(ClusterArticle.cluster_id)
                )
            ).all()
        )
        ent_sets = await _cluster_entity_sets(session, ids)
        topic_sets = await _cluster_topic_sets(session, ids)

    # Union-find over confirmed merge pairs.
    parent = {c: c for c in ids}

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra

    tight, loose = settings.cluster_merge_threshold_tight, settings.cluster_merge_threshold_loose
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            dist = 1.0 - float(sim[i][j])
            if dist >= loose:
                continue
            if dist < tight:
                _union(ids[i], ids[j])  # pure-semantic: merge, no confirmation
            elif (ent_sets.get(ids[i], set()) & ent_sets.get(ids[j], set())) or (
                topic_sets.get(ids[i], set()) & topic_sets.get(ids[j], set())
            ):
                _union(ids[i], ids[j])  # loose band: only with a shared entity/topic

    groups: dict[int, list[int]] = {}
    for c in ids:
        groups.setdefault(_find(c), []).append(c)
    merges = [g for g in groups.values() if len(g) >= 2]
    if not merges:
        return

    merged = 0
    for group in merges:
        survivor = max(group, key=lambda c: (counts.get(c, 0), -c))  # most articles, tie → lowest id
        losers = [c for c in group if c != survivor]
        try:
            async with async_session() as session:
                await _merge_into(session, survivor, losers)
                await session.commit()
            from app.services.summarizer import schedule_summary

            schedule_summary(survivor)  # article set changed → regenerate the summary in the background
            merged += len(losers)
        except Exception as e:  # noqa: BLE001 — one bad group must not abort the rest
            logger.warning("cluster_merge_failed", survivor=survivor, losers=losers, error=str(e))

    logger.info(
        "cluster_reconcile_complete",
        candidate_clusters=len(ids),
        groups=len(merges),
        clusters_merged=merged,
    )
