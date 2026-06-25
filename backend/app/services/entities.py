"""G1: the global entity backbone.

This module owns reading AND (in later slices) writing the backbone. The two read helpers below are
pure SQL — they surface "who/what is in this story" + "what else touches them", no LLM.

G2 BREADCRUMB: any future LENS that reads graph output must widen its `_source_hash` to include
entity ids + content version + persona/depth (+ user scope at G2), or it will serve stale/cross-tenant
answers. The G1 endpoints are uncached pure-SQL reads, so the trap does not bite yet.
"""
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import ArticleEntity, ClusterArticle, Entity, EntityAlias, StoryCluster
from app.schemas import EntityExtraction
from app.services import llm, retrieval

logger = structlog.get_logger()


async def cluster_entities(db: AsyncSession, cluster_id: int) -> list[dict]:
    """Cast strip: salient entities across this cluster's articles, deduped by entity (max salience),
    highest-salience first, capped at graph_max_entities_per_cluster."""
    sal = func.max(ArticleEntity.salience).label("salience")
    q = (
        select(Entity.id, Entity.canonical_name, Entity.kind, sal)
        .join(ArticleEntity, ArticleEntity.entity_id == Entity.id)
        .join(ClusterArticle, ClusterArticle.article_id == ArticleEntity.article_id)
        .where(ClusterArticle.cluster_id == cluster_id)
        .group_by(Entity.id, Entity.canonical_name, Entity.kind)
        .order_by(sal.desc())
        .limit(settings.graph_max_entities_per_cluster)
    )
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
    raw = await llm.generate(
        build_extraction_prompt(text_),
        schema={"entities": []},  # truthy → JSON mode; contents ignored by llm.generate
        model=settings.graph_extraction_model,
        force_platform_key=settings.graph_use_platform_key,  # bill the platform, not the owner's key
    )
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

async def backfill_entities() -> None:
    """APScheduler job: extract entities for SETTLED, CHANGED clusters. Modeled on
    summarizer.backfill_summaries — selects candidate ids in one session, then processes each in
    its OWN session/transaction (independent of the already-committed clustering loop). On-change
    skip via the source_hash stored in extra_json.graph. Dark unless graph_extraction_enabled."""
    from app.services import lenses  # lazy — avoids any import-time weight/cycle

    if not settings.graph_extraction_enabled:
        return

    async with async_session() as session:
        rows = (
            await session.execute(
                select(StoryCluster.id)
                .join(ClusterArticle, ClusterArticle.cluster_id == StoryCluster.id)
                .group_by(StoryCluster.id)
                .having(func.count(ClusterArticle.id) >= settings.graph_extract_min_sources)
                .order_by(StoryCluster.created_at.desc())
                .limit(settings.graph_extract_batch_size)
            )
        ).all()
        cluster_ids = [r[0] for r in rows]

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
