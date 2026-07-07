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
# Per-user generation, bumped on every invalidate(). rails_for_user captures it before it starts
# building and only writes the cache back if it's unchanged — so a create/delete/seen that lands
# mid-build isn't masked by a stale write-back for a full TTL (compare-and-set).
_generation: dict[int, int] = {}


def invalidate(user_id: int) -> None:
    _cache.pop(user_id, None)
    _generation[user_id] = _generation.get(user_id, 0) + 1


def _escape_like(s: str) -> str:
    r"""Escape LIKE metacharacters so a saved-search phrase is matched LITERALLY — otherwise a
    stray % or _ in the phrase acts as a wildcard and widens the keyword leg. Pairs with
    ilike(..., escape='\\')."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _admit(dist: float | None, keyword_hit: bool, entity_hit: bool, *, semantic_available: bool) -> bool:
    """The precision guard. When the semantic leg ran, a cluster joins a saved-search rail iff it's
    semantically near AND a proper-noun hit confirms it, OR it's a very tight pure-semantic match —
    keyword/entity hits are ONLY confirmation, never independent admission (else "US Iran war" pulls
    in every Iran story via the entity leg). ONLY when the semantic leg was entirely unavailable
    (embeddings down) do we degrade to a keyword-or-entity match. Distinguishing these two `dist is
    None` cases is the whole point — a keyword/entity hit that merely fell outside the ANN top-k is
    NOT the same as "we couldn't embed the query at all"."""
    if not semantic_available:
        return keyword_hit or entity_hit  # degraded: proper-noun match only
    if dist is None:
        return False  # semantic ran but this candidate wasn't near enough to surface — reject
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

    # Keyword leg: literal substring in the title (recency-scoped; LIKE metacharacters escaped so
    # "%" / "_" in the phrase don't act as wildcards). Bounded to the newest rails_ann_k so a broad
    # phrase ("India") can't union thousands of rows into one IN(...).
    like = f"%{_escape_like(phrase)}%"
    kw_ids = set(
        (
            await db.execute(
                select(Article.id)
                .where(
                    Article.title.ilike(like, escape="\\"),
                    Article.published_at.isnot(None),
                    Article.published_at >= since,
                )
                .order_by(Article.published_at.desc())
                .limit(settings.rails_ann_k)
            )
        ).scalars()
    )

    # Entity leg: the phrase (or a token of it) matches a known entity alias → its recent articles.
    ent_ids = await _entity_leg(db, phrase, since)

    # Admit per the precision guard. When the semantic leg ran, ONLY its top-k are candidates —
    # keyword/entity legs are confirmation flags, never independent admission (see _admit). When it
    # was unavailable, the proper-noun legs are all we have, so THEY become the candidate set.
    semantic_available = emb is not None
    candidates = set(dist_by_article) if semantic_available else (kw_ids | ent_ids)
    admitted = {
        aid
        for aid in candidates
        if _admit(
            dist_by_article.get(aid),
            aid in kw_ids,
            aid in ent_ids,
            semantic_available=semantic_available,
        )
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
                .order_by(Article.published_at.desc())
                .limit(settings.rails_ann_k)  # bound: a hot entity ("Iran") can tag hundreds in 72h
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


# Kind priority when two follows collide on a normalized value: keep the most precise rail. A `topic`
# rail is an exact ArticleTopic membership match; an `entity` rail is a resolved-entity match; a
# `saved_search` rail is a fuzzy hybrid over the same words. So topic > entity > saved_search.
_KIND_PRIORITY = {"topic": 0, "entity": 1, "saved_search": 2}


def _dedupe_follows(follows: list[Follow]) -> list[Follow]:
    """Collapse rail-able follows that share a value (case-insensitively) ACROSS kinds, so "News You
    Follow" never renders two rails with an identical header. This collision is legal — uq_follow keys
    on (user_id, kind, value), so a `topic` 'AI' and a `saved_search` 'AI' are two distinct rows — and
    the interests↔topic-follow unify makes it likely: chips/onboarding auto-create the `topic` follow
    while /follows and "Follow this search" create a `saved_search` follow on the SAME free text.

    Keep the highest-priority kind per normalized value (topic beats saved_search — see _KIND_PRIORITY);
    same-priority ties keep the first seen, which is the newest since `follows` arrive created_at desc.
    Input order is otherwise preserved (each surviving follow stays at its own position)."""
    winner: dict[str, Follow] = {}
    for f in follows:
        key = (f.value or "").strip().lower()
        cur = winner.get(key)
        if cur is None or _KIND_PRIORITY.get(f.kind, 99) < _KIND_PRIORITY.get(cur.kind, 99):
            winner[key] = f
    kept = {f.id for f in winner.values()}
    return [f for f in follows if f.id in kept]


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

    # Capture the generation BEFORE building. If a create/delete/seen invalidate() bumps it while we
    # await DB calls below, we skip the stale write-back rather than mask the mutation for a full TTL.
    gen_at_start = _generation.get(user_id, 0)
    since = datetime.now(timezone.utc) - timedelta(hours=settings.rails_recency_hours)
    follows = (
        await db.execute(
            select(Follow)
            .where(Follow.user_id == user_id, Follow.kind.in_(RAIL_KINDS))
            .order_by(Follow.created_at.desc())
        )
    ).scalars().all()
    # Collapse cross-kind collisions on the same value (e.g. topic 'AI' + saved_search 'AI') so we
    # don't render two rails with an identical header. Do it BEFORE building so the dropped follow's
    # eval never runs.
    follows = _dedupe_follows(follows)

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

    # Compare-and-set: only cache if no invalidate() landed while we were building (see gen_at_start).
    if _generation.get(user_id, 0) == gen_at_start:
        _cache[user_id] = (now + settings.rails_cache_ttl_seconds, rails)
    return rails
