"""G1: the global entity backbone.

This module owns reading AND (in later slices) writing the backbone. The two read helpers below are
pure SQL — they surface "who/what is in this story" + "what else touches them", no LLM.

G2 BREADCRUMB: any future LENS that reads graph output must widen its `_source_hash` to include
entity ids + content version + persona/depth (+ user scope at G2), or it will serve stale/cross-tenant
answers. The G1 endpoints are uncached pure-SQL reads, so the trap does not bite yet.
"""
import structlog
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import (
    Article, ArticleEntity, ClusterArticle, Entity, EntityAlias, Source, SourceType,
    StoryCluster, UserEntityRelevance,
)
from app.schemas import EntityExtraction
from app.services import llm, retrieval

logger = structlog.get_logger()


_LN2 = 0.6931471805599453  # ln(2) for the half-life decay


def _decayed_relevance_sql():
    """The shared half-life decay aggregate: coalesce(max(engagement_raw * exp(-ln2*age/half_life)), 0),
    age clamped >= 0 (clock-skew guard). Used by BOTH cluster_entities (its beta term) and the surface
    scorer so the two cannot drift. MUST be used inside a query grouped per entity (max over that
    entity's single UER row)."""
    age_days = func.greatest(
        0.0, func.extract("epoch", func.now() - UserEntityRelevance.last_event_at) / 86400.0
    )
    return func.coalesce(
        func.max(UserEntityRelevance.engagement_raw
                 * func.exp(-_LN2 * age_days / settings.uer_half_life_days)),
        0.0,
    )


async def cluster_entities(db: AsyncSession, cluster_id: int, user_id: int | None = None) -> list[dict]:
    """Cast strip: salient entities across this cluster's articles, deduped by entity (max salience),
    capped. With uer_enabled + a user_id, the owner's followed/read entities rank up via
    alpha*salience + beta*decayed_relevance (decay = exp(-ln2 * age_days / half_life), read-time).
    With uer_enabled off (or no user) the output is byte-identical to G1 (ordered by salience)."""
    sal = func.max(ArticleEntity.salience).label("salience")
    base = (
        select(Entity.id, Entity.canonical_name, Entity.kind, sal)
        .join(ArticleEntity, ArticleEntity.entity_id == Entity.id)
        .join(ClusterArticle, ClusterArticle.article_id == ArticleEntity.article_id)
        .where(ClusterArticle.cluster_id == cluster_id)
        .group_by(Entity.id, Entity.canonical_name, Entity.kind)
    )
    cap = settings.graph_max_entities_per_cluster
    if settings.uer_enabled and user_id is not None:
        decayed = _decayed_relevance_sql()  # shared clock-skew-clamped half-life decay
        rank = settings.uer_rank_alpha * func.max(ArticleEntity.salience) + settings.uer_rank_beta * decayed
        q = (
            # LEFT JOIN is safe from row fan-out: (user_id, entity_id) is the UER primary key.
            base.outerjoin(
                UserEntityRelevance,
                and_(UserEntityRelevance.entity_id == Entity.id,
                     UserEntityRelevance.user_id == user_id),
            )
            .order_by(rank.desc(), Entity.id.asc())  # stable tiebreak → no cast-strip reshuffle
            .limit(cap)
        )
    else:
        q = base.order_by(func.max(ArticleEntity.salience).desc(), Entity.id.asc()).limit(cap)
    rows = (await db.execute(q)).all()
    return [
        {"id": r.id, "canonical_name": r.canonical_name, "kind": r.kind, "salience": r.salience}
        for r in rows
    ]


async def entity_clusters(db: AsyncSession, entity_id: int, limit: int = 10) -> list[dict]:
    """'Appears in' rail: other recent clusters whose articles mention this entity, newest first."""
    q = (
        select(StoryCluster.id, StoryCluster.title, StoryCluster.created_at)
        .join(ClusterArticle, ClusterArticle.cluster_id == StoryCluster.id)
        .join(ArticleEntity, ArticleEntity.article_id == ClusterArticle.article_id)
        .where(ArticleEntity.entity_id == entity_id)
        .group_by(StoryCluster.id, StoryCluster.title, StoryCluster.created_at)
        .order_by(StoryCluster.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    return [{"cluster_id": r.id, "title": r.title, "created_at": r.created_at} for r in rows]


async def resolve_existing(db: AsyncSession, value: str) -> int | None:
    """G1 S7: exact-or-alias lookup for an entity by surface form → entity id, or None. A cheap
    forward-compat hook for entity follows (resolution only — no follows schema change, no merge)."""
    q = (value or "").strip().lower()
    if not q:
        return None
    ent = (await db.execute(select(Entity).where(Entity.name_norm == q))).scalars().first()
    if ent is not None:
        return ent.id
    ea = (await db.execute(select(EntityAlias).where(EntityAlias.alias_norm == q))).scalars().first()
    return ea.entity_id if ea is not None else None


async def bump_relevance(db: AsyncSession, user_id: int, entity_id: int, *, source: str, weight: float) -> None:
    """G2: upsert the per-user affinity row for (user, entity) — add `weight`, refresh last_event_at.
    Called on follow (source='follow') + reading feedback (source='feedback'). Decay is computed at
    READ time from engagement_raw + last_event_at (no cron), so this only accumulates raw signal."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    row = (
        await db.execute(
            select(UserEntityRelevance).where(
                UserEntityRelevance.user_id == user_id,
                UserEntityRelevance.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(UserEntityRelevance(user_id=user_id, entity_id=entity_id, source=source,
                                   engagement_raw=weight, last_event_at=now))
    else:
        row.engagement_raw = (row.engagement_raw or 0.0) + weight
        row.last_event_at = now


async def bump_relevance_for_article(db: AsyncSession, user_id: int, article_id: int, *,
                                     source: str, weight: float) -> int:
    """G2 S4: bump per-user relevance for every entity mentioned in an article (a feedback signal).
    Returns the number of entities bumped."""
    ent_ids = (
        await db.execute(select(ArticleEntity.entity_id).where(ArticleEntity.article_id == article_id))
    ).scalars().all()
    for eid in ent_ids:
        await bump_relevance(db, user_id, eid, source=source, weight=weight)
    return len(ent_ids)


# ── Surface personalization (G2 S5): one shared per-cluster relevance score ──────────


async def score_clusters_relevance(
    db: AsyncSession, cluster_ids: list[int], user_id: int | None
) -> dict[int, float]:
    """Per-cluster user affinity = AVG over the cluster's entities of the decayed relevance (the SAME
    decay as the cast strip, via _decayed_relevance_sql). The ONE primitive that feed / briefing /
    search consume to personalize their ranking. Returns {cluster_id: score}; clusters with entities
    but no signal score 0.0, clusters with no entities are absent — callers treat absent as 0.0.

    Fast-returns {} when personalization is off, there is no user, or no ids → a disabled flag or a
    zero-relevance user is a guaranteed no-op on every surface. Deliberately OMITS alpha*salience
    (unlike cluster_entities): global salience is the baseline each surface already encodes via
    recency / search rank / topic weight, so re-injecting it here would reorder a no-signal user by
    popularity and break the no-op invariant. The user_id filter sits on the LEFT JOIN's ON clause
    (the primary multi-user isolation control; RLS is defense-in-depth). The join cannot fan out:
    (user_id, entity_id) is the UER primary key."""
    if not settings.uer_enabled or user_id is None or not cluster_ids:
        return {}
    per_entity = (
        select(
            ClusterArticle.cluster_id.label("cid"),
            ArticleEntity.entity_id.label("eid"),
            _decayed_relevance_sql().label("decayed"),
        )
        .join(ArticleEntity, ArticleEntity.article_id == ClusterArticle.article_id)
        .outerjoin(
            UserEntityRelevance,
            and_(UserEntityRelevance.entity_id == ArticleEntity.entity_id,
                 UserEntityRelevance.user_id == user_id),
        )
        .where(ClusterArticle.cluster_id.in_(cluster_ids))
        .group_by(ClusterArticle.cluster_id, ArticleEntity.entity_id)
        .subquery()
    )
    q = select(per_entity.c.cid, func.avg(per_entity.c.decayed)).group_by(per_entity.c.cid)
    rows = (await db.execute(q)).all()
    return {cid: float(score) for cid, score in rows if score is not None}


async def score_cluster_relevance(db: AsyncSession, cluster_id: int, user_id: int | None) -> float:
    """Single-cluster convenience wrapper over score_clusters_relevance (tests / one-off callers)."""
    return (await score_clusters_relevance(db, [cluster_id], user_id)).get(cluster_id, 0.0)


# ── Extraction + resolution (G1 S3-S4) ──────────────────────────────────────────────

def build_extraction_prompt(cluster_text: str) -> str:
    """The JSON shape lives in the PROMPT — llm.generate's `schema` arg only flips JSON mode on,
    it does not enforce structure (EntityExtraction.model_validate is the real guard)."""
    return (
        "Extract the salient named entities from the news coverage below — only the people, "
        "organizations, and places that genuinely matter to the story (not every proper noun).\n\n"
        f"<coverage>\n{cluster_text}\n</coverage>\n\n"
        "Respond ONLY as JSON of this exact shape:\n"
        '{"entities": [{"canonical_name": "<full canonical name>", '
        '"kind": "person|org|place|other", "salience": <0..1 importance to THIS story>, '
        '"aliases": ["<other surface forms>"]}]}\n'
        f"Return at most {settings.graph_max_entities_per_cluster} entities, highest salience first."
    )


async def extract_entities(cluster: StoryCluster, articles: list) -> EntityExtraction | None:
    """One JSON-mode LLM pass over the cluster's full bodies (D1 seam). Returns the validated
    extraction, or None when the model returns valid JSON of the wrong shape (logged + skipped)."""
    text_ = retrieval.cluster_text(cluster, articles, depth_pref="standard")
    try:
        # No model= → generate() resolves the OWNER's active provider + that provider's model
        # (never a hardcoded gpt-* id sent to Claude). force_platform_key bills the platform key.
        raw = await llm.generate(
            build_extraction_prompt(text_),
            schema={"entities": []},  # truthy → JSON mode; contents ignored by llm.generate
            force_platform_key=settings.graph_use_platform_key,
        )
    except llm.LLMUnavailable:
        return None  # no platform key for the active provider → skip; never crash the backfill loop
    try:
        return EntityExtraction.model_validate(raw)
    except Exception as e:  # noqa: BLE001 — wrong-shape JSON is skipped, never fatal
        logger.warning("entity_extraction_invalid", cluster_id=getattr(cluster, "id", None), error=str(e))
        return None


async def resolve_and_persist(db: AsyncSession, articles: list, extraction: EntityExtraction) -> None:
    """Resolve each extracted entity (exact name → alias → create), attach its aliases, and link it
    to the cluster's articles. Idempotent (uq_article_entity); precision-biased (no embedding NN /
    auto-merge in G1). Flushes only — the caller owns the transaction/commit."""
    article_ids = [a.id for a in articles]
    selected = sorted(
        (e for e in extraction.entities if e.salience >= settings.graph_salience_floor),
        key=lambda e: e.salience,
        reverse=True,
    )[: settings.graph_max_entities_per_cluster]

    for ext in selected:
        q = ext.canonical_name.lower()
        # 1. exact (kind, name_norm) — uses ix_entities_kind_name
        entity = (
            await db.execute(select(Entity).where(Entity.kind == ext.kind, Entity.name_norm == q))
        ).scalar_one_or_none()
        # 2. alias: the extracted name is a known alias of an existing entity
        if entity is None:
            ea = (
                await db.execute(select(EntityAlias).where(EntityAlias.alias_norm == q))
            ).scalars().first()
            if ea is not None:
                entity = await db.get(Entity, ea.entity_id)
        # 3. create
        if entity is None:
            entity = Entity(canonical_name=ext.canonical_name, name_norm=q, kind=ext.kind)
            db.add(entity)
            await db.flush()

        for al in ext.aliases:
            aln = al.strip().lower()
            if not aln or aln == entity.name_norm:
                continue
            dup = (
                await db.execute(
                    select(EntityAlias).where(
                        EntityAlias.entity_id == entity.id, EntityAlias.alias_norm == aln
                    )
                )
            ).scalar_one_or_none()
            if dup is None:
                db.add(EntityAlias(entity_id=entity.id, alias=al.strip(), alias_norm=aln, source="extraction"))

        for aid in article_ids:
            link = (
                await db.execute(
                    select(ArticleEntity).where(
                        ArticleEntity.article_id == aid, ArticleEntity.entity_id == entity.id
                    )
                )
            ).scalar_one_or_none()
            if link is None:
                db.add(ArticleEntity(article_id=aid, entity_id=entity.id,
                                     salience=ext.salience, confidence=ext.salience))
    await db.flush()


# ── Decoupled backfill job (G1 S5) ──────────────────────────────────────────────────

async def _extraction_candidates(session) -> list[int]:
    """Cluster ids eligible for entity extraction.

    News/general clusters must be 'settled' (>= graph_extract_min_sources articles). #89: a
    research-tier cluster is eligible at just 1 source — a paper's abstract won't cluster with news
    (cosine 0.15), so it stays a singleton, and we still want its people/institutions extracted.
    """
    research_articles = func.count(
        case((Source.source_type == SourceType.research, 1))
    )
    rows = (
        await session.execute(
            select(StoryCluster.id)
            .join(ClusterArticle, ClusterArticle.cluster_id == StoryCluster.id)
            .join(Article, Article.id == ClusterArticle.article_id)
            .join(Source, Source.id == Article.source_id)
            .group_by(StoryCluster.id)
            .having(
                or_(
                    func.count(ClusterArticle.id) >= settings.graph_extract_min_sources,
                    research_articles >= settings.graph_extract_research_min_sources,
                )
            )
            .order_by(StoryCluster.created_at.desc())
            .limit(settings.graph_extract_batch_size)
        )
    ).all()
    return [r[0] for r in rows]


async def backfill_entities() -> None:
    """APScheduler job: extract entities for SETTLED, CHANGED clusters. Modeled on
    summarizer.backfill_summaries — selects candidate ids in one session, then processes each in
    its OWN session/transaction (independent of the already-committed clustering loop). On-change
    skip via the source_hash stored in extra_json.graph. Dark unless graph_extraction_enabled."""
    from app.services import lenses  # lazy — avoids any import-time weight/cycle

    if not settings.graph_extraction_enabled:
        return

    async with async_session() as session:
        cluster_ids = await _extraction_candidates(session)

    if not cluster_ids:
        return

    extracted = 0
    for cid in cluster_ids:
        async with async_session() as s:  # own session + transaction per cluster
            cluster, articles = await lenses._load(s, cid)
            if cluster is None or not articles:
                continue
            sh = lenses._source_hash(articles)
            stored = (cluster.extra_json or {}).get("graph", {}).get("source_hash")
            if stored == sh:
                continue  # settled + unchanged → no-op (no LLM call)
            ext = await extract_entities(cluster, articles)
            if ext is None:
                continue
            await resolve_and_persist(s, articles, ext)
            # write the on-change marker + commit (one commit per cluster, via the lens JSONB merge)
            await lenses._cache_write(s, cluster, "extra_json", "graph", sh,
                                      {"entities": len(ext.entities)})
            extracted += 1

    logger.info("entity_backfill_complete", candidates=len(cluster_ids), extracted=extracted)
