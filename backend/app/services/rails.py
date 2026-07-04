"""WS-2 (#112): "News You Follow" rails — evaluate a user's follows into recency-scoped story rails.

A follow becomes a live category:
- saved_search ("US Iran war") — HYBRID: pgvector ANN (semantic, exposing distance) + ILIKE keyword
  + entity-alias leg, admitted by the precision guard so "US Iran war" doesn't drag in every
  Middle-East story. Degrades to keyword+entity when embeddings are unavailable.
- topic — clusters whose articles carry that topic.
- entity — clusters featuring that entity (article_entities).
- source follows are NOT rails (the tier gate already surfaces them in the feed).

Each rail is independent (one follow's failure never kills the others), 72h-windowed, grouped by
cluster, with a per-follow `new_count` since follows.last_viewed_at. A 60s per-user response cache
keeps a home render from re-running N hybrid queries every visit.

    ┌─ follows(saved_search|topic|entity) ─┐
    │  per follow (isolated try/except):    │
    │    saved_search → hybrid → cluster set │
    │    topic/entity → membership → set     │──▶ group by cluster ▶ light stories ▶ new_count
    └───────────────────────────────────────┘
"""
import time

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Article,
    ArticleEntity,
    ArticleTopic,
    ClusterArticle,
    EntityAlias,
    Follow,
    StoryCluster,
    Topic,
)

logger = structlog.get_logger()

RAIL_KINDS = ("saved_search", "topic", "entity")

# 60s per-user cache: {user_id: (expires_epoch, payload)}. Process-local (a restart re-warms); a
# follow create/delete or a /seen tap busts the caller's entry (see invalidate()).
_cache: dict[int, tuple[float, list]] = {}


def invalidate(user_id: int) -> None:
    _cache.pop(user_id, None)


def _admit(dist: float | None, keyword_hit: bool, entity_hit: bool) -> bool:
    """The precision guard. A cluster joins a saved-search rail iff it's semantically near AND a
    proper-noun hit confirms it, OR it's a very tight pure-semantic match. dist is None when the
    semantic leg was unavailable — then a keyword/entity hit alone admits (keyword-only fallback)."""
    if dist is None:
        return keyword_hit or entity_hit
    if dist < settings.rails_dist_tight:
        return True
    if dist < settings.rails_dist_loose and (keyword_hit or entity_hit):
        return True
    return False


async def _recent_cluster_of(db: AsyncSession, article_ids: list[int], since) -> dict[int, int]:
    """Map article_id -> cluster_id for articles published within the window (drops unclustered /
    stale). One query, no N+1."""
    if not article_ids:
        return {}
    rows = (
        await db.execute(
            select(ClusterArticle.article_id, ClusterArticle.cluster_id)
            .join(Article, Article.id == ClusterArticle.article_id)
            .where(
                ClusterArticle.article_id.in_(article_ids),
                Article.published_at.isnot(None),
                Article.published_at >= since,
            )
        )
    ).all()
    return {aid: cid for aid, cid in rows}


async def evaluate_saved_search(db: AsyncSession, phrase: str, since) -> set[int]:
    """Hybrid eval of a free-text follow → the set of cluster ids in the window. Logs a distance
    histogram so the precision thresholds can be calibrated from real data (the WS-2 pre-gate)."""
    from app.services.embeddings import embed_query_cached, vector_literal

    phrase = (phrase or "").strip()
    if not phrase:
        return set()

    # Semantic leg: ANN with the recency predicate INSIDE the WHERE (post-filtering top-k could be
    # saturated by old articles), exposing the distance the precision guard needs.
    dist_by_article: dict[int, float] = {}
    try:
        emb = await embed_query_cached(phrase)
    except Exception:  # noqa: BLE001 — semantic leg is best-effort; keyword/entity still run
        emb = None
    if emb is not None:
        rows = (
            await db.execute(
                text(
                    "SELECT id, embedding <=> :v AS dist FROM articles "
                    "WHERE embedding IS NOT NULL AND published_at IS NOT NULL AND published_at >= :since "
                    "ORDER BY embedding <=> :v LIMIT :k"
                ),
                {"v": vector_literal(emb), "since": since, "k": settings.rails_ann_k},
            )
        ).all()
        dist_by_article = {aid: float(d) for aid, d in rows}
        if dist_by_article:
            _log_distance_histogram(phrase, list(dist_by_article.values()))

    # Keyword leg: exact substring in the title (recency-scoped).
    like = f"%{phrase}%"
    kw_ids = set(
        (
            await db.execute(
                select(Article.id).where(
                    Article.title.ilike(like),
                    Article.published_at.isnot(None),
                    Article.published_at >= since,
                )
            )
        ).scalars()
    )

    # Entity leg: the phrase (or a token of it) matches a known entity alias → its recent articles.
    ent_ids = await _entity_leg(db, phrase, since)

    # Union of every candidate, then admit per the precision guard.
    candidates = set(dist_by_article) | kw_ids | ent_ids
    admitted = {
        aid
        for aid in candidates
        if _admit(dist_by_article.get(aid), aid in kw_ids, aid in ent_ids)
    }
    return set((await _recent_cluster_of(db, sorted(admitted), since)).values())


async def _entity_leg(db: AsyncSession, phrase: str, since) -> set[int]:
    """Recent article ids whose entities match the phrase by exact alias (normalized). Cheap
    proper-noun anchor — "US Iran war" hits the 'iran'/'united states' aliases."""
    from app.services.filings import norm_company  # reuse the punctuation-stripping normalizer

    keys = {norm_company(phrase)} | {norm_company(tok) for tok in phrase.split()}
    keys = {k for k in keys if len(k) >= 3}
    if not keys:
        return set()
    ent_ids = (
        await db.execute(select(EntityAlias.entity_id).where(EntityAlias.alias_norm.in_(sorted(keys))))
    ).scalars().all()
    if not ent_ids:
        return set()
    return set(
        (
            await db.execute(
                select(ArticleEntity.article_id)
                .join(Article, Article.id == ArticleEntity.article_id)
                .where(
                    ArticleEntity.entity_id.in_(sorted(set(ent_ids))),
                    Article.published_at.isnot(None),
                    Article.published_at >= since,
                )
            )
        ).scalars()
    )


def _log_distance_histogram(phrase: str, dists: list[float]) -> None:
    dists = sorted(dists)
    n = len(dists)
    logger.info(
        "rail_distance_histogram",
        phrase=phrase[:60],
        n=n,
        min=round(dists[0], 4),
        p25=round(dists[n // 4], 4),
        p50=round(dists[n // 2], 4),
        max=round(dists[-1], 4),
        under_tight=sum(1 for d in dists if d < settings.rails_dist_tight),
        under_loose=sum(1 for d in dists if d < settings.rails_dist_loose),
    )


async def evaluate_topic(db: AsyncSession, topic_name: str, since) -> set[int]:
    """Clusters whose recent articles carry the followed topic (value = topic name)."""
    return set(
        (
            await db.execute(
                select(ClusterArticle.cluster_id)
                .join(ArticleTopic, ArticleTopic.article_id == ClusterArticle.article_id)
                .join(Topic, Topic.id == ArticleTopic.topic_id)
                .join(Article, Article.id == ClusterArticle.article_id)
                .where(
                    func.lower(Topic.name) == topic_name.strip().lower(),
                    Article.published_at.isnot(None),
                    Article.published_at >= since,
                )
                .distinct()
            )
        ).scalars()
    )


async def evaluate_entity(db: AsyncSession, follow: Follow, since) -> set[int]:
    """Clusters featuring the followed entity. Prefer the resolved entity_id (chip path); else
    resolve the string value to an entity."""
    from app.services import entities as ent

    eid = follow.entity_id
    if eid is None:
        eid = await ent.resolve_existing(db, follow.value)
    if eid is None:
        return set()
    return set(
        (
            await db.execute(
                select(ClusterArticle.cluster_id)
                .join(ArticleEntity, ArticleEntity.article_id == ClusterArticle.article_id)
                .join(Article, Article.id == ClusterArticle.article_id)
                .where(
                    ArticleEntity.entity_id == eid,
                    Article.published_at.isnot(None),
                    Article.published_at >= since,
                )
                .distinct()
            )
        ).scalars()
    )


async def _cluster_id_since(db: AsyncSession, cluster_ids: list[int]):
    """Per-cluster newest article published_at (for new_count) + a light story payload — cached-summary
    ONLY (no on-demand LLM: a rails render must be cheap)."""
    if not cluster_ids:
        return {}, {}
    story_rows = (
        await db.execute(
            select(StoryCluster).where(StoryCluster.id.in_(cluster_ids))
        )
    ).scalars().all()
    newest = (
        await db.execute(
            select(ClusterArticle.cluster_id, func.max(Article.published_at), func.count())
            .join(Article, Article.id == ClusterArticle.article_id)
            .where(ClusterArticle.cluster_id.in_(cluster_ids))
            .group_by(ClusterArticle.cluster_id)
        )
    ).all()
    meta = {cid: (ts, cnt) for cid, ts, cnt in newest}
    return {s.id: s for s in story_rows}, meta


async def rails_for_user(db: AsyncSession, user_id: int) -> list[dict]:
    """The whole "News You Follow" payload for a user: one rail per rail-able follow, newest-first,
    each with ≤N stories in the 72h window and a badge new_count. Source follows are excluded.

    Per-follow isolation: a single follow's eval failure drops THAT rail and logs — the others render.
    """
    from datetime import datetime, timedelta, timezone

    if not settings.rails_enabled:
        return []
    now = time.time()
    cached = _cache.get(user_id)
    if cached and cached[0] > now:
        return cached[1]

    since = datetime.now(timezone.utc) - timedelta(hours=settings.rails_recency_hours)
    follows = (
        await db.execute(
            select(Follow)
            .where(Follow.user_id == user_id, Follow.kind.in_(RAIL_KINDS))
            .order_by(Follow.created_at.desc())
        )
    ).scalars().all()

    rails: list[dict] = []
    for f in follows:
        try:
            if f.kind == "saved_search":
                cluster_ids = await evaluate_saved_search(db, f.value, since)
            elif f.kind == "topic":
                cluster_ids = await evaluate_topic(db, f.value, since)
            else:  # entity
                cluster_ids = await evaluate_entity(db, f, since)
        except Exception as e:  # noqa: BLE001 — isolate: one bad rail must not blank the section
            logger.warning("rail_eval_failed", follow_id=f.id, kind=f.kind, error=str(e))
            continue

        stories_by_id, meta = await _cluster_id_since(db, sorted(cluster_ids))
        # newest-first by the cluster's newest article; cap to N.
        ordered = sorted(
            cluster_ids,
            key=lambda cid: (meta.get(cid, (None, 0))[0] or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        top = ordered[: settings.rails_stories_per_follow]
        new_count = sum(
            1
            for cid in cluster_ids
            if f.last_viewed_at is None
            or (meta.get(cid, (None, 0))[0] is not None and meta[cid][0] > f.last_viewed_at)
        )
        rails.append(
            {
                "follow_id": f.id,
                "kind": f.kind,
                "value": f.value,
                "total": len(cluster_ids),
                "new_count": new_count,
                "stories": [
                    {
                        "cluster_id": cid,
                        "title": stories_by_id[cid].title if cid in stories_by_id else "",
                        "summary": (stories_by_id[cid].summary if cid in stories_by_id else None),
                        "source_count": meta.get(cid, (None, 1))[1],
                    }
                    for cid in top
                    if cid in stories_by_id
                ],
            }
        )

    _cache[user_id] = (now + settings.rails_cache_ttl_seconds, rails)
    return rails
