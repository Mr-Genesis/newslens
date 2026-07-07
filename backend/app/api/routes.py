import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session, get_db
from app.services.auth import current_user_id, get_current_user
from app.models import (
    Article,
    ArticleTopic,
    ClusterArticle,
    FeedbackType,
    Follow,
    Impression,
    Source,
    SourceType,
    StoryCluster,
    Topic,
    User,
    UserFeedback,
    UserPreference,
    UserSetting,
)
from app.schemas import (
    ArticleOut,
    AskRequest,
    BriefingResponse,
    DigestItem,
    DigestResponse,
    FollowCreate,
    FollowOut,
    BriefingStory,
    ClusterDetailOut,
    ClusterSourceCard,
    DiscoverCardOut,
    DWELL_MAX_MS,
    FeedbackCreate,
    FeedbackOut,
    ImpressionsBatch,
    FeedResponse,
    AnthropicKeyUpdate,
    GeminiKeyUpdate,
    HealthResponse,
    KeyTestResult,
    ProfileOut,
    ProfileUpdate,
    SavedArticleOut,
    SavedListResponse,
    SourceOut,
    StatsResponse,
    SurfaceCTR,
    SwipeRequest,
    TopicOut,
    TopicListResponse,
    UserSettingsOut,
    UserSettingsUpdate,
)

logger = structlog.get_logger()
router = APIRouter()


@router.get("/", include_in_schema=False)
async def root():
    """Landing for the bare API host (Render's platform probe + humans hitting the base URL).
    Without this, GET / 404s and pollutes the logs even though the service is healthy."""
    return {
        "service": "NewsLens API",
        "version": "0.1.0",
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    db_ok = False
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.warning("health_check_db_failed", error=str(e))
        # Fallback: try raw asyncpg connection
        try:
            import asyncpg
            from app.config import settings

            # Extract connection params from async URL
            url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
            conn = await asyncpg.connect(url)
            await conn.fetchval("SELECT 1")
            await conn.close()
            db_ok = True
        except Exception as e2:
            logger.warning("health_check_fallback_failed", error=str(e2))

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db=db_ok,
    )


@router.get("/pipeline")
async def pipeline_status(db: AsyncSession = Depends(get_db)):
    """At-a-glance data-pipeline health (unauthenticated, like /health). Makes a stalled stage obvious:
    if `articles.by_embedding_status` is all pending/failed and `clusters.total` is ~0, embeddings
    are dead → nothing clusters → story details can't open. `last_embedding_error` names WHY (quota /
    auth / no_key) so the cause is visible without the log stream."""
    from app.services import embeddings as _embeddings

    status_rows = (
        await db.execute(
            select(Article.embedding_status, func.count()).group_by(Article.embedding_status)
        )
    ).all()
    by_status: dict[str, int] = {}
    for st, cnt in status_rows:
        key = st.value if hasattr(st, "value") else str(st)
        by_status[key] = cnt

    total_clusters = (
        await db.execute(select(func.count()).select_from(StoryCluster))
    ).scalar_one()
    articles_clustered = (
        await db.execute(select(func.count(func.distinct(ClusterArticle.article_id))))
    ).scalar_one()
    latest_article = (await db.execute(select(func.max(Article.fetched_at)))).scalar_one()
    latest_cluster = (await db.execute(select(func.max(StoryCluster.created_at)))).scalar_one()

    return {
        "articles": {"total": sum(by_status.values()), "by_embedding_status": by_status},
        "clusters": {"total": total_clusters, "articles_clustered": articles_clustered},
        "freshness": {
            "latest_article_fetched_at": latest_article.isoformat() if latest_article else None,
            "latest_cluster_created_at": latest_cluster.isoformat() if latest_cluster else None,
        },
        "last_embedding_error": _embeddings.last_embedding_error(),
    }


@router.get("/health/fresh")
async def health_fresh(db: AsyncSession = Depends(get_db)):
    """WS-8 (#118): a freshness ALARM (unauthenticated). 503 when the newest article was fetched more
    than `freshness_alarm_minutes` ago — the app itself asserts the pipeline is running, so an EXTERNAL
    pinger (cron-job.org) can email on non-200 independent of GitHub Actions (which auto-disables after
    60d of repo inactivity — exactly when hands-off monitoring matters). Returns the body on both paths
    so the pinger email carries the age."""
    from app.config import settings as _s
    from fastapi.responses import JSONResponse

    latest = (await db.execute(select(func.max(Article.fetched_at)))).scalar_one()
    now = datetime.now(timezone.utc)
    age_min = None if latest is None else (now - latest).total_seconds() / 60.0
    fresh = age_min is not None and age_min <= _s.freshness_alarm_minutes
    body = {
        "fresh": fresh,
        "latest_article_fetched_at": latest.isoformat() if latest else None,
        "age_minutes": round(age_min, 1) if age_min is not None else None,
        "threshold_minutes": _s.freshness_alarm_minutes,
    }
    return body if fresh else JSONResponse(body, status_code=503)


@router.get("/feed", response_model=FeedResponse, dependencies=[Depends(get_current_user)])
async def get_feed(
    topic: int | None = None,
    source_type: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    as_of: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page
    from app.config import settings as app_settings

    query = (
        select(Article)
        .options(selectinload(Article.source))
        .order_by(Article.published_at.desc().nullslast())
    )

    if topic:
        query = query.join(Article.topics).where(
            Article.topics.any(topic_id=topic)
        )

    # Phase 1: persona-gate the research/expert tiers — a source is in the feed only if it's news,
    # or clears the credibility floor and matches the user's profession-derived audience tags.
    from app.services import audience as _audience
    from app.services import pubmed as _pubmed
    _profession, _locale, _pv = await _user_profession_locale(db)
    # #88: keyword map first, LLM fallback for the long tail (cached on persona_version).
    _tags = await _audience.resolve_tags(_profession, user_id=current_user_id(), persona_version=_pv)
    _user_specialty = _pubmed.term_for_profession(_profession)  # #94: for the specialty rank boost
    # WS-7 (#117): locale region-affinity applies ONLY after an explicit profile save (persona_version
    # > 1) and when enabled — else None → ranking.locale_mult is a strict ×1.0 no-op.
    _locale_user = _locale if (app_settings.locale_affinity_enabled and _pv > 1) else None
    _followed = await _audience.followed_source_ids(db, current_user_id())  # #81 opt-in override
    _base_allowed = Article.source_id.in_(
        _audience.allowed_source_ids(
            _tags, floor=app_settings.credibility_feed_floor, followed_source_ids=_followed
        )
    )
    # Phase 3: filings are audience=[] so the source-gate hides them, but one exchange firehose carries
    # thousands of companies — a per-source follow can't express "only MY companies". Widen the gate
    # with a per-ARTICLE branch: a filing is visible iff its company entity is in the caller's OWN
    # watchlist/follows. Empty set (no watchlist, or feature off) → the OR collapses to the legacy
    # source-gate → byte-identical feed.
    from app.services import filings as _filings
    _filing_ent_ids = await _filings.watchlisted_entity_ids(db, current_user_id())
    if _filing_ent_ids:
        from sqlalchemy import and_, or_

        from app.models import ArticleEntity
        query = query.where(
            or_(
                _base_allowed,
                and_(
                    Article.source_id.in_(
                        select(Source.id).where(Source.source_type == SourceType.filing)
                    ),
                    Article.id.in_(
                        select(ArticleEntity.article_id).where(
                            ArticleEntity.entity_id.in_(sorted(_filing_ent_ids))
                        )
                    ),
                ),
            )
        )
    else:
        query = query.where(_base_allowed)

    # #82: source-type filter chips ("All / News / Research / Experts / Official"). Composes with the
    # persona gate above — filtering to a tier never bypasses it. "news" = the non-gated tiers.
    if source_type and source_type.lower() != "all":
        from fastapi import HTTPException
        st = source_type.lower()
        _gated_types = list(_audience.gated_source_types())
        if st == "news":
            type_cond = Source.source_type.notin_(_gated_types)
        elif st in ("research", "expert", "official", "filing"):
            type_cond = Source.source_type == SourceType(st)
        else:
            raise HTTPException(status_code=400, detail="invalid source_type")
        query = query.where(Article.source_id.in_(select(Source.id).where(type_cond)))

    # WS-3 (#113): the as_of pagination cursor. When the client threads a cursor (page ≥ 2), pin the
    # pool to fetched_at <= as_of so new ingest mid-scroll can't shift page boundaries (duplicate/drop
    # rows) — on BOTH the personalized and legacy paths (they share the identical top-shift bug).
    # Omitting as_of (the first page) leaves the query UNFILTERED — byte-identical legacy behavior, and
    # avoids clock skew excluding a just-ingested row — while we still hand back as_of=now to pin later
    # pages. A stale cursor whose window is empty recovers with a fresh now() (see response_as_of below).
    now = datetime.now(timezone.utc)
    if as_of is not None:
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        query = query.where(Article.fetched_at <= as_of)

    # G2: when personalizing, fetch a bounded recent pool and rerank it (recency + entity relevance)
    # BEFORE paginating, so a high-affinity story can cross page boundaries within the horizon. When
    # off, take the exact legacy path (count + offset/limit) → byte-identical response.
    if app_settings.uer_enabled:
        pool_result = await db.execute(query.limit(app_settings.uer_feed_pool_size))
        articles = pool_result.scalars().all()
        total = len(articles)  # personalization horizon = the pool
    else:
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar_one()
        results = await db.execute(query.offset(offset).limit(per_page))
        articles = results.scalars().all()

    # Resolve cluster membership + per-cluster source count in aggregate (no N+1).
    article_ids = [a.id for a in articles]
    art_to_cluster: dict[int, int] = {}
    cluster_source_count: dict[int, int] = {}
    clusters_with_summary: set[int] = set()
    if article_ids:
        ca_rows = (
            await db.execute(
                select(ClusterArticle.article_id, ClusterArticle.cluster_id).where(
                    ClusterArticle.article_id.in_(article_ids)
                )
            )
        ).all()
        for art_id, cl_id in ca_rows:
            art_to_cluster[art_id] = cl_id
        cluster_ids = list(set(art_to_cluster.values()))
        if cluster_ids:
            cnt_rows = (
                await db.execute(
                    select(ClusterArticle.cluster_id, func.count(ClusterArticle.id))
                    .where(ClusterArticle.cluster_id.in_(cluster_ids))
                    .group_by(ClusterArticle.cluster_id)
                )
            ).all()
            cluster_source_count = {cl_id: cnt for cl_id, cnt in cnt_rows}
            sum_rows = (
                await db.execute(
                    select(StoryCluster.id).where(
                        StoryCluster.id.in_(cluster_ids),
                        StoryCluster.summary.isnot(None),
                    )
                )
            ).all()
            clusters_with_summary = {row[0] for row in sum_rows}

    # G2: rerank the pool by the recency+relevance blend, then slice the requested page. When off,
    # `articles` is already the legacy page, so page_articles == articles (byte-identical).
    if app_settings.uer_enabled:
        from app.services import entities

        rel_cluster_ids = list({cid for cid in art_to_cluster.values()})
        scores = await entities.score_clusters_relevance(db, rel_cluster_ids, current_user_id())
        pub_ts = {a.id: (a.published_at.timestamp() if a.published_at else None) for a in articles}
        present = [t for t in pub_ts.values() if t is not None]
        lo, hi = (min(present), max(present)) if present else (0.0, 0.0)
        ratio = app_settings.uer_feed_blend_ratio
        from app.services import ranking  # WS-5 (#115): the extracted, parity-tested feed blend

        def _blend(a: Article) -> float:
            src_specialty = (a.source.credibility_meta or {}).get("specialty") if a.source else None
            return ranking.blend_score(
                ranking.recency_norm(pub_ts[a.id], lo, hi),
                scores.get(art_to_cluster.get(a.id), 0.0),
                ranking.credibility_mult(a.source.credibility_score if a.source else None),
                ranking.specialty_mult(src_specialty, _user_specialty),
                ratio,
            ) * ranking.locale_mult(a.source.region if a.source else None, _locale_user)

        blends = {a.id: _blend(a) for a in articles}
        articles.sort(
            key=lambda a: (blends[a.id], pub_ts[a.id] if pub_ts[a.id] is not None else float("-inf"), a.id),
            reverse=True,
        )
        page_articles = articles[offset:offset + per_page]
    else:
        page_articles = articles

    article_outs = []
    for a in page_articles:
        cl_id = art_to_cluster.get(a.id)
        article_outs.append(
            ArticleOut(
                id=a.id,
                title=a.title,
                snippet=a.snippet,
                url=a.url,
                source=SourceOut.model_validate(a.source),
                published_at=a.published_at,
                embedding_status=a.embedding_status,
                source_count=cluster_source_count.get(cl_id, 1) if cl_id else 1,
                cluster_id=cl_id,
                has_ai_summary=cl_id in clusters_with_summary,
            )
        )

    # Compute real explore ratio from recent feedback
    feedback_result = await db.execute(
        select(UserFeedback.feedback_type)
        .where(UserFeedback.user_id == current_user_id())
        .order_by(UserFeedback.created_at.desc())
        .limit(app_settings.feedback_window_size)
    )
    recent_feedback = [row[0] for row in feedback_result.all()]
    if recent_feedback:
        explore_signals = sum(1 for f in recent_feedback if f == FeedbackType.less)
        explore_ratio = max(
            app_settings.min_explore_ratio,
            min(app_settings.max_explore_ratio, explore_signals / len(recent_feedback)),
        )
    else:
        explore_ratio = app_settings.default_explore_ratio

    # WS-3 (#113): the cursor echoed to the client. Normally the pinned as_of (or now() on the first
    # page). But a client-supplied cursor whose window is now empty (predates all data / pruned) is
    # stale — hand back a FRESH now() so the client restarts pagination instead of looping on an empty
    # page. (Distinct from "caught up": there total > 0 and only the page slice is empty.)
    response_as_of = as_of if as_of is not None else now
    if as_of is not None and total == 0:
        response_as_of = now

    return FeedResponse(
        articles=article_outs,
        total=total,
        page=page,
        per_page=per_page,
        explore_ratio=explore_ratio,
        as_of=response_as_of,
    )


@router.get("/clusters/{cluster_id}", response_model=ClusterDetailOut, dependencies=[Depends(get_current_user)])
async def get_cluster(cluster_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(StoryCluster)
        .options(
            selectinload(StoryCluster.articles)
            .selectinload(ClusterArticle.article)
            .selectinload(Article.source)
        )
        .where(StoryCluster.id == cluster_id)
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        # Fallback: briefing may pass article IDs when no clusters exist.
        # Return a synthetic single-article cluster so the detail page works.
        art_result = await db.execute(
            select(Article)
            .options(selectinload(Article.source))
            .where(Article.id == cluster_id)
        )
        article = art_result.scalar_one_or_none()
        if not article:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Cluster not found")

        # Mark article as read
        existing_read = await db.execute(
            select(UserFeedback).where(
                UserFeedback.user_id == current_user_id(),
                UserFeedback.article_id == article.id,
                UserFeedback.feedback_type == FeedbackType.read,
            )
        )
        if existing_read.scalar_one_or_none() is None:
            db.add(UserFeedback(
                user_id=current_user_id(),
                article_id=article.id,
                feedback_type=FeedbackType.read,
            ))
            await db.commit()

        return ClusterDetailOut(
            id=cluster_id,
            title=article.title,
            summary=article.snippet,
            created_at=article.published_at or article.fetched_at or datetime.now(timezone.utc),
            coherence=None,  # single-article synthetic cluster has no real coherence
            sources=[
                ClusterSourceCard(
                    article=ArticleOut(
                        id=article.id,
                        title=article.title,
                        snippet=article.snippet,
                        url=article.url,
                        source=SourceOut.model_validate(article.source),
                        published_at=article.published_at,
                        embedding_status=article.embedding_status,
                    ),
                    is_free=not article.source.is_paywalled,
                )
            ],
        )

    # Non-blocking summary: return a snippet fallback instantly and generate the real summary in the
    # background (schedule_summary) so the next view is warm. NEVER mutate cluster.summary here — the
    # db.commit() below (for read marks) would persist the snippet and make backfill skip this cluster.
    response_summary = cluster.summary
    if not cluster.summary:
        from app.services.summarizer import snippet_summary, schedule_summary
        response_summary = snippet_summary([ca.article.snippet or "" for ca in cluster.articles])
        schedule_summary(cluster.id)

    # Mark all articles in cluster as read
    article_ids = [ca.article.id for ca in cluster.articles]
    for aid in article_ids:
        existing_read = await db.execute(
            select(UserFeedback).where(
                UserFeedback.user_id == current_user_id(),
                UserFeedback.article_id == aid,
                UserFeedback.feedback_type == FeedbackType.read,
            )
        )
        if existing_read.scalar_one_or_none() is None:
            db.add(UserFeedback(
                user_id=current_user_id(),
                article_id=aid,
                feedback_type=FeedbackType.read,
            ))
    await db.commit()

    # Sort: free sources first, then paywalled
    source_cards = []
    for ca in cluster.articles:
        source_cards.append(
            ClusterSourceCard(
                article=ArticleOut(
                    id=ca.article.id,
                    title=ca.article.title,
                    snippet=ca.article.snippet,
                    url=ca.article.url,
                    source=SourceOut.model_validate(ca.article.source),
                    published_at=ca.article.published_at,
                    embedding_status=ca.article.embedding_status,
                ),
                is_free=not ca.article.source.is_paywalled,
            )
        )

    # Free first, then paywalled
    source_cards.sort(key=lambda x: (not x.is_free, x.article.title))

    from app.services import lenses

    return ClusterDetailOut(
        id=cluster.id,
        title=cluster.title,
        summary=response_summary,
        created_at=cluster.created_at,
        # Real source-agreement ratio when a consensus pass is cached; else stored value / heuristic.
        coherence=lenses.cluster_coherence(cluster, [ca.article for ca in cluster.articles]),
        sources=source_cards,
    )


@router.get("/articles/{article_id}", dependencies=[Depends(get_current_user)])
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    """Single-article detail for briefing-fallback stories (article not clustered yet).

    Resolves the article's cluster id when one exists so the client can upgrade to the
    full deep dive instead of the single-article view.
    """
    from fastapi import HTTPException

    from app.schemas import ArticleDetail

    article = (
        await db.execute(
            select(Article)
            .options(selectinload(Article.source))
            .where(Article.id == article_id)
        )
    ).scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="article not found")

    cluster_id = (
        await db.execute(
            select(ClusterArticle.cluster_id)
            .where(ClusterArticle.article_id == article_id)
            .limit(1)
        )
    ).scalar_one_or_none()

    return ArticleDetail(
        id=article.id,
        title=article.title,
        snippet=article.snippet,
        url=article.url,
        source_name=article.source.name if article.source else "Unknown",
        is_paywalled=bool(article.source.is_paywalled) if article.source else False,
        published_at=article.published_at,
        cluster_id=cluster_id,
    )


@router.get("/topics", response_model=TopicListResponse, dependencies=[Depends(get_current_user)])
async def get_topics(db: AsyncSession = Depends(get_db)):
    """Per-user topic split (was "all topics → your_topics" MVP):
    - your_topics: the caller's subscribed topics (UserPreference), by weight — shown even if quiet.
    - explore_topics: topics the caller has NOT subscribed to that currently have content.
    - trending_topics: top topics by RECENT (7d) article volume — a public, non-personalized ranking.
    """
    from datetime import timedelta

    topics = (await db.execute(select(Topic).order_by(Topic.name))).scalars().all()
    by_id = {t.id: t for t in topics}

    # Total per-topic article counts (drives article_count + explore ranking).
    counts = dict(
        (
            await db.execute(
                select(ArticleTopic.topic_id, func.count(ArticleTopic.article_id)).group_by(
                    ArticleTopic.topic_id
                )
            )
        ).all()
    )
    # Recent (7d) volume per topic — drives "trending". Uses fetched_at (NOT NULL) rather than
    # published_at, so undated items (feeds with no parseable date) still count as recent.
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = dict(
        (
            await db.execute(
                select(ArticleTopic.topic_id, func.count(ArticleTopic.article_id))
                .join(Article, Article.id == ArticleTopic.article_id)
                .where(Article.fetched_at >= recent_cutoff)
                .group_by(ArticleTopic.topic_id)
            )
        ).all()
    )

    # The caller's subscriptions (UserPreference), highest weight first.
    subs = (
        await db.execute(
            select(UserPreference.topic_id, UserPreference.weight).where(
                UserPreference.user_id == current_user_id()
            )
        )
    ).all()
    sub_weight = {tid: w for tid, w in subs}
    sub_ids = set(sub_weight)

    def out(t: Topic, is_explore: bool = False) -> TopicOut:
        return TopicOut(id=t.id, name=t.name, article_count=counts.get(t.id, 0), is_explore=is_explore)

    your_topics = [
        out(by_id[tid])
        for tid in sorted(sub_ids & by_id.keys(), key=lambda i: (-sub_weight[i], by_id[i].name))
    ]
    explore = [
        out(t, is_explore=True)
        for t in sorted(
            (t for t in topics if t.id not in sub_ids and counts.get(t.id, 0) > 0),
            key=lambda t: (-counts.get(t.id, 0), t.name),
        )
    ][:10]
    trending = [
        out(t)
        for t in sorted(
            (t for t in topics if recent.get(t.id, 0) > 0),
            key=lambda t: (-recent.get(t.id, 0), t.name),
        )
    ][:5]

    return TopicListResponse(your_topics=your_topics, explore_topics=explore, trending_topics=trending)


@router.post("/feedback", response_model=FeedbackOut, status_code=201, dependencies=[Depends(get_current_user)])
async def create_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    # WS-1 dwell: read + cluster_id upserts duration onto the EXISTING auto-read row instead of
    # creating a new one. Target = the cluster's min article id (deterministic — the cluster open
    # marks ALL its articles read, so "the" read row needs one canonical choice; the synthetic
    # fallback path, where cluster_id IS an article id, resolves the same way).
    if body.feedback_type == FeedbackType.read and body.cluster_id is not None:
        target = (
            await db.execute(
                select(func.min(ClusterArticle.article_id)).where(
                    ClusterArticle.cluster_id == body.cluster_id
                )
            )
        ).scalar_one_or_none()
        if target is None:
            # briefing fallback: the "cluster" was a bare article id
            target = (
                await db.execute(select(Article.id).where(Article.id == body.cluster_id))
            ).scalar_one_or_none()
        if target is None:
            # Dwell for a story that no longer exists (deleted / stale deep-link). Fire-and-forget
            # no-op — do NOT fall through to a plain insert: body.article_id on this path is the
            # cluster id we just proved absent from `articles`, so the insert would 500 on the FK.
            logger.info("dwell_target_missing", cluster_id=body.cluster_id)
            from datetime import datetime, timezone
            return FeedbackOut(id=0, article_id=body.article_id,
                               feedback_type=body.feedback_type,
                               created_at=datetime.now(timezone.utc))
        row = (
            await db.execute(
                select(UserFeedback).where(
                    UserFeedback.user_id == current_user_id(),
                    UserFeedback.article_id == target,
                    UserFeedback.feedback_type == FeedbackType.read,
                )
            )
        ).scalars().first()
        if row is None:
            row = UserFeedback(user_id=current_user_id(), article_id=target,
                               feedback_type=FeedbackType.read)
            db.add(row)
        if body.duration_ms is not None:
            dur = min(body.duration_ms, DWELL_MAX_MS)  # clamp, never reject
            row.duration_ms = max(row.duration_ms or 0, dur)  # GREATEST
        if body.surface:
            row.surface = body.surface
        await db.commit()
        await db.refresh(row)
        logger.info("dwell_recorded", cluster_id=body.cluster_id,
                    duration_ms=row.duration_ms, surface=row.surface)
        return FeedbackOut.model_validate(row)

    feedback = UserFeedback(
        user_id=current_user_id(),
        article_id=body.article_id,
        feedback_type=body.feedback_type,
        surface=body.surface,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    logger.info(
        "feedback_created",
        article_id=body.article_id,
        feedback_type=body.feedback_type.value,
    )

    from app.config import settings
    from app.services import entities

    # G2: positive feedback seeds per-user relevance for the article's entities (decay at read
    # time). WS-1: 'less' now writes a NEGATIVE bump — dislike demotes the story's entities.
    weight = settings.uer_less_weight if body.feedback_type == FeedbackType.less \
        else settings.uer_follow_weight
    n = await entities.bump_relevance_for_article(
        db, current_user_id(), body.article_id, source="feedback", weight=weight
    )
    if n:
        await db.commit()

    return FeedbackOut.model_validate(feedback)


@router.post("/impressions", status_code=202, dependencies=[Depends(get_current_user)])
async def record_impressions(body: ImpressionsBatch, db: AsyncSession = Depends(get_db)):
    """WS-1 (#111): batched impression logging — what the user SAW per surface. Deduped per
    (user, story, surface, day) via the COALESCE expression index (ON CONFLICT DO NOTHING);
    capped per day (drop + log beyond); unknown story ids dropped (a stale client buffer must
    not 500 the whole batch). Fire-and-forget contract: always 202 with counts."""
    from app.config import settings as app_settings

    if not app_settings.impressions_enabled or not body.items:
        return {"accepted": 0, "dropped": len(body.items)}

    uid = current_user_id()
    today_count = (
        await db.execute(
            select(func.count()).select_from(Impression).where(
                Impression.user_id == uid, Impression.day == func.current_date()
            )
        )
    ).scalar_one()
    budget = max(0, app_settings.impression_daily_cap - today_count)

    # Pre-validate targets in bulk — a deleted article/cluster in a stale buffer must not blow the
    # batch on FK violation (which would poison the transaction mid-flush).
    cluster_ids = {i.cluster_id for i in body.items if i.cluster_id is not None}
    article_ids = {i.article_id for i in body.items if i.article_id is not None}
    ok_clusters = set(
        (await db.execute(select(StoryCluster.id).where(StoryCluster.id.in_(cluster_ids)))).scalars()
    ) if cluster_ids else set()
    ok_articles = set(
        (await db.execute(select(Article.id).where(Article.id.in_(article_ids)))).scalars()
    ) if article_ids else set()

    accepted = 0
    dropped = 0
    for item in body.items:
        if accepted >= budget:
            dropped += 1
            continue
        cid = item.cluster_id if item.cluster_id in ok_clusters else None
        aid = item.article_id if item.article_id in ok_articles else None
        if cid is None and aid is None:
            dropped += 1
            continue
        result = await db.execute(
            text(
                "INSERT INTO impressions (user_id, cluster_id, article_id, surface, day) "
                "VALUES (:u, :c, :a, :s, CURRENT_DATE) "
                "ON CONFLICT (user_id, COALESCE(cluster_id, 0), COALESCE(article_id, 0), surface, day) "
                "DO NOTHING"
            ),
            {"u": uid, "c": cid, "a": aid, "s": item.surface},
        )
        accepted += result.rowcount or 0
    await db.commit()
    if dropped:
        logger.info("impressions_dropped", user_id=uid, dropped=dropped, accepted=accepted)
    return {"accepted": accepted, "dropped": dropped}


# ── Briefing ──────────────────────────────────────────────


def _extract_impact_headline(impact_json: dict | None) -> str | None:
    """Best-effort headline from a cluster's cached impact_json (E6).

    impact_json is keyed by sub-lens (e.g. ``prof:<hash>``) -> {"source_hash", "data"}
    where ``data`` holds {"headline": ..., "dimensions": [...]}. Returns the first
    non-empty cached headline found, or None. Makes NO LLM calls.
    """
    if not isinstance(impact_json, dict):
        return None
    for entry in impact_json.values():
        if not isinstance(entry, dict):
            continue
        data = entry.get("data")
        if isinstance(data, dict):
            headline = data.get("headline")
            if isinstance(headline, str) and headline.strip():
                return headline.strip()
    return None


# Source-taxonomy categories → reader-facing chip names (used when an article has no topic
# row yet — the source's own category beats a blanket "General").
SOURCE_CATEGORY_DISPLAY = {
    "world": "World",
    "technology": "Technology",
    "science": "Science",
    "business": "Business",
    "national": "India",
    "policy": "Policy",
    "startup": "Start-up",
    # Phase 1 source expansion — new categories introduced by the 80-feed seed.
    "research": "Research",
    "health": "Health",
    "finance": "Finance",
    "economics": "Economics",
    "legal": "Legal",
    "sports": "Sports",
    "entertainment": "Entertainment",
    "ai": "AI",
}


@router.get("/briefing", response_model=BriefingResponse, dependencies=[Depends(get_current_user)])
async def get_briefing(db: AsyncSession = Depends(get_db)):
    """
    Returns AI-generated daily briefing built from story clusters.
    Uses real AI summaries, dynamic coherence scores, read state tracking,
    and explore/exploit ordering based on user preferences.
    """
    from app.config import settings as app_settings

    # Get read article IDs for this user
    read_result = await db.execute(
        select(UserFeedback.article_id).where(
            UserFeedback.user_id == current_user_id(),
            UserFeedback.feedback_type == FeedbackType.read,
        )
    )
    read_article_ids = set(row[0] for row in read_result.all())

    # Get user topic preference weights
    pref_result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user_id())
    )
    prefs = {p.topic_id: p.weight for p in pref_result.scalars().all()}

    # Phase 1: persona-gate the candidate window — a cluster is eligible only if at least one of
    # its articles comes from a source this user may see (news, or a floor-clearing research/expert
    # source matching their profession). Research/expert clusters are singletons, so this hides a
    # cardiology paper from everyone except doctors, at the briefing floor.
    from sqlalchemy import exists as _sa_exists
    from app.services import audience as _audience
    _profession, _, _pv = await _user_profession_locale(db)
    # #80/#88: keyword map first, LLM fallback for the long tail (cached on persona_version).
    _tags = await _audience.resolve_tags(_profession, user_id=current_user_id(), persona_version=_pv)
    _followed = await _audience.followed_source_ids(db, current_user_id())  # #81 opt-in override
    _allowed = _audience.allowed_source_ids(
        _tags, floor=app_settings.credibility_briefing_floor, followed_source_ids=_followed
    )
    _visible = _sa_exists().where(
        ClusterArticle.cluster_id == StoryCluster.id,
        ClusterArticle.article_id == Article.id,
        Article.source_id.in_(_allowed),
    )

    # Get recent clusters with their articles + sources + topics
    result = await db.execute(
        select(StoryCluster)
        .where(_visible)
        .options(
            selectinload(StoryCluster.articles)
            .selectinload(ClusterArticle.article)
            .selectinload(Article.source),
            selectinload(StoryCluster.articles)
            .selectinload(ClusterArticle.article)
            .selectinload(Article.topics)
            .selectinload(ArticleTopic.topic),
        )
        .order_by(StoryCluster.created_at.desc())
        .limit(20)
    )
    clusters = result.scalars().all()

    # G2: per-cluster entity relevance for this user (one aggregate; {} when off / zero-signal).
    from app.services import entities, lenses

    cluster_scores = await entities.score_clusters_relevance(
        db, [c.id for c in clusters], current_user_id()
    )

    # Track stories with their preference weights for explore/exploit sorting
    stories: list[BriefingStory] = []
    story_weights: dict[int, float] = {}  # cluster_id -> blended weight

    for cluster in clusters:
        # Count unique sources and gather metadata
        source_names = set()
        first_snippet = None
        category = "General"
        topic_id = None
        region = None
        cluster_article_ids = []
        for ca in cluster.articles:
            source_names.add(ca.article.source.name)
            cluster_article_ids.append(ca.article.id)
            if first_snippet is None and ca.article.snippet:
                first_snippet = ca.article.snippet
            if region is None and ca.article.source and ca.article.source.region == "in":
                region = "India"
            if category == "General" and ca.article.topics:
                for at in ca.article.topics:
                    if at.topic:
                        category = at.topic.name
                        topic_id = at.topic_id
                        break
            # No topic row yet → classify by the source's own category (every seeded source
            # carries one) instead of defaulting everything to "General" (device-QA #3b).
            if category == "General" and ca.article.source and ca.article.source.category:
                category = SOURCE_CATEGORY_DISPLAY.get(
                    ca.article.source.category, category
                )

        # Non-blocking summary: use the cached real one if present, else return the snippet fallback
        # instantly and warm the real summary in the background (schedule_summary) for the next view.
        summary = cluster.summary
        coherence = cluster.coherence
        if not summary:
            from app.services.summarizer import schedule_summary
            schedule_summary(cluster.id)
            summary = first_snippet or "No summary available."
            sentences = summary.split(". ")
            if len(sentences) > 2:
                summary = ". ".join(sentences[:2]) + "."

        # Coherence: the real source-agreement ratio when a consensus pass is cached for this cluster,
        # else the stored value, else the honest source-overlap heuristic (all in cluster_coherence).
        coherence = lenses.cluster_coherence(cluster, [ca.article for ca in cluster.articles])

        # Check if any article in this cluster has been read
        is_read = any(aid in read_article_ids for aid in cluster_article_ids)

        # Track preference weight for explore/exploit sorting. G2: blend entity relevance ADDITIVELY
        # (orthogonal to the explicit topic preference — a followed-entity story can climb even with
        # no topic preference; a zero-signal user gets +0, so ordering is identical to today).
        pref_weight = prefs.get(topic_id, 0.0) if topic_id else 0.0
        # #80: "in your field" bonus — a research/expert cluster whose source audience overlaps the
        # user's profession tags gets a small additive lift so it reliably reaches the top-8. A
        # profession-less user has empty tags → never matches → briefing ordering is unchanged. An
        # audience-null general source (visible to everyone) is NOT "your field" → no bonus.
        # official counts for the "in your field" bonus too (a Fed decision belongs in a finance
        # user's top-8); filing never matches (audience=[] overlaps nothing) — safe in the same set.
        _gated_tiers = _audience.gated_source_types()
        field_match = any(
            ca.article.source
            and ca.article.source.source_type in _gated_tiers
            and ca.article.source.audience
            and (set(ca.article.source.audience) & _tags)
            for ca in cluster.articles
        )
        # #78: expose the gated tier (if any) so the card can show a RESEARCH/EXPERT/OFFICIAL badge.
        tier = next(
            (
                ca.article.source.source_type.value
                for ca in cluster.articles
                if ca.article.source and ca.article.source.source_type in _gated_tiers
            ),
            None,
        )
        story_weights[cluster.id] = (
            pref_weight
            + app_settings.uer_briefing_blend_weight * cluster_scores.get(cluster.id, 0.0)
            + (app_settings.credibility_briefing_bonus if field_match else 0.0)
        )

        # E6: best-effort WIIFM headline from ALREADY-cached impact_json (no LLM calls).
        impact_headline = _extract_impact_headline(cluster.impact_json)

        stories.append(
            BriefingStory(
                title=cluster.title,
                summary=summary,
                cluster_id=cluster.id,
                category=category,
                region=region,
                source_count=len(source_names),
                coherence=coherence,
                is_read=is_read,
                impact_headline=impact_headline,
                tier=tier,
            )
        )

    # Explore/exploit sorting: top 6 by preference weight (exploit), last 2 low-weight (explore)
    if len(stories) > 8:
        stories.sort(key=lambda s: story_weights.get(s.cluster_id, 0.0), reverse=True)
        exploit = stories[:6]
        remaining = stories[6:]
        remaining.sort(key=lambda s: story_weights.get(s.cluster_id, 0.0))
        explore = remaining[:2]
        stories = exploit + explore

    stories = stories[:8]

    # Fallback: if no clusters, build briefing from recent articles. Apply the SAME persona gate as
    # the cluster path (#81) — otherwise a profession-less user with sparse content would leak gated
    # research/expert articles here, defeating the gate. `_allowed` already folds in followed sources.
    if not stories:
        article_result = await db.execute(
            select(Article)
            .options(
                selectinload(Article.source),
                selectinload(Article.topics).selectinload(ArticleTopic.topic),
            )
            .where(Article.snippet.isnot(None), Article.source_id.in_(_allowed))
            .order_by(Article.published_at.desc().nullslast())
            .limit(8)
        )
        articles = article_result.scalars().all()

        # Resolve each fallback article's REAL cluster id (None when unclustered). Never pass the
        # article id as cluster_id: the two id sequences race past each other, so a masqueraded id
        # sends the deep-dive/lenses to a nonexistent or WRONG cluster.
        ca_rows = (
            await db.execute(
                select(ClusterArticle.article_id, ClusterArticle.cluster_id).where(
                    ClusterArticle.article_id.in_([a.id for a in articles] or [0])
                )
            )
        ).all()
        article_cluster = {aid: cid for aid, cid in ca_rows}

        for a in articles:
            snippet = a.snippet or ""
            sentences = snippet.split(". ")
            summary = ". ".join(sentences[:2]) + "." if len(sentences) > 1 else snippet
            # Classify: article topic → source's own category → General. (The old version
            # mapped 10 hardcoded Western outlet names, so every Indian source fell to
            # "General" — device-QA #3b.)
            category = "General"
            for at in a.topics:
                if at.topic:
                    category = at.topic.name
                    break
            if category == "General" and a.source and a.source.category:
                category = SOURCE_CATEGORY_DISPLAY.get(a.source.category, "General")
            region = "India" if (a.source and a.source.region == "in") else None
            is_read = a.id in read_article_ids

            stories.append(
                BriefingStory(
                    title=a.title,
                    summary=summary,
                    cluster_id=article_cluster.get(a.id),
                    article_id=a.id,  # unclustered fallback cards open /story?aid=N
                    category=category,
                    region=region,
                    source_count=1,
                    coherence=0.70,
                    is_read=is_read,
                )
            )

    # Compute real explore ratio from recent feedback
    feedback_result = await db.execute(
        select(UserFeedback.feedback_type)
        .where(UserFeedback.user_id == current_user_id())
        .order_by(UserFeedback.created_at.desc())
        .limit(app_settings.feedback_window_size)
    )
    recent_feedback = [row[0] for row in feedback_result.all()]
    if recent_feedback:
        explore_signals = sum(1 for f in recent_feedback if f == FeedbackType.less)
        explore_ratio = max(
            app_settings.min_explore_ratio,
            min(app_settings.max_explore_ratio, explore_signals / len(recent_feedback)),
        )
    else:
        explore_ratio = app_settings.default_explore_ratio

    return BriefingResponse(
        stories=stories,
        generated_at=datetime.now(timezone.utc),
        explore_ratio=explore_ratio,
    )


# ── Discover ─────────────────────────────────────────────


@router.get("/discover/deck", response_model=list[DiscoverCardOut])
async def get_discover_deck(
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a deck of 20-30 cards for the discover/swipe interface.
    MVP: returns recent articles with cluster context.
    """
    from app.config import settings as app_settings
    from app.services import audience as _audience

    # ALL gated tiers (research/expert/official/filing) are excluded from the news pool, but the
    # deck's random opt-in sample deliberately EXCLUDES filing — a stranger's 10-Q must never be a
    # discover card. Filings reach users only via watchlist/follow.
    _gated_types = list(_audience.gated_source_types())
    _sample_types = [SourceType.research, SourceType.expert, SourceType.official]
    _opts = (
        selectinload(Article.source),
        selectinload(Article.topics).selectinload(ArticleTopic.topic),
    )
    # #83: the discover deck is the OPT-IN surface for the gated tiers. Reserve up to ~5 slots for
    # research/expert/official cards regardless of the user's profession (this is exactly where a
    # non-matching user discovers and follows them); fill the rest from the NON-gated (news) pool so
    # gated cards only ever arrive via this flagged reserved sample — never through the main pool.
    gated_result = await db.execute(
        select(Article).options(*_opts)
        .join(Source, Article.source_id == Source.id)
        .where(Article.snippet.isnot(None), Source.source_type.in_(_sample_types))
        .order_by(func.random())
        .limit(app_settings.discover_gated_slots)
    )
    gated_articles = gated_result.scalars().all()
    news_result = await db.execute(
        select(Article).options(*_opts)
        .join(Source, Article.source_id == Source.id)
        .where(Article.snippet.isnot(None), Source.source_type.notin_(_gated_types))
        .order_by(func.random())
        .limit(25 - len(gated_articles))
    )
    articles = list(gated_articles) + list(news_result.scalars().all())

    # #103: resolve each article's cached tension line (extra_json['tension']) — a pure cache lookup,
    # no LLM in the deck path. The backfill job (#98) generates + refreshes it out of band.
    art_ids = [a.id for a in articles]
    tension_by_article: dict[int, str] = {}
    if art_ids:
        ca_rows = (await db.execute(
            select(ClusterArticle.article_id, ClusterArticle.cluster_id)
            .where(ClusterArticle.article_id.in_(art_ids)))).all()
        a2c = {aid: cid for aid, cid in ca_rows}
        cids = list(set(a2c.values()))
        c2line: dict[int, str] = {}
        if cids:
            for cid, extra in (await db.execute(
                    select(StoryCluster.id, StoryCluster.extra_json)
                    .where(StoryCluster.id.in_(cids)))).all():
                entry = (extra or {}).get("tension")
                line = (entry.get("data") or {}).get("line") if isinstance(entry, dict) else None
                if line:
                    c2line[cid] = line
        tension_by_article = {aid: c2line[cid] for aid, cid in a2c.items() if cid in c2line}

    cards: list[DiscoverCardOut] = []
    for i, article in enumerate(articles):
        # Get topic info
        topic_id = 0
        topic_name = "General"
        if article.topics:
            for at in article.topics:
                if at.topic:
                    topic_id = at.topic.id
                    topic_name = at.topic.name
                    break

        # Build facts from snippet
        snippet = article.snippet or ""
        sentences = [s.strip() for s in snippet.split(". ") if s.strip()]
        facts = sentences[:3] if sentences else ["No details available."]

        src = article.source
        is_gated = bool(src and src.source_type in _gated_types)
        cards.append(
            DiscoverCardOut(
                id=i + 1,
                article_id=article.id,
                title=article.title,
                tension_line=tension_by_article.get(article.id) or article.title,  # #103: cached, else title
                facts=facts,
                sources=[src.name] if src else [],
                topic_id=topic_id,
                topic_name=topic_name,
                coherence=0.82,  # placeholder
                source_id=src.id if src else None,
                source_type=src.source_type.value if (src and src.source_type) else None,
                is_gated=is_gated,
                is_preprint=bool(src and src.is_preprint),
                author_name=src.author_name if src else None,
                credibility_score=src.credibility_score if src else None,
            )
        )

    return cards


@router.post("/discover/swipe", status_code=204, dependencies=[Depends(get_current_user)])
async def record_swipe(
    body: SwipeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Records a swipe action and adjusts user preferences.
    Right = +0.1 weight, Left = -0.2 weight, Up = +0.3 weight.
    """
    # Map swipe direction to feedback type
    feedback_map = {
        "right": FeedbackType.interesting,
        "left": FeedbackType.less,
        "up": FeedbackType.save,
    }
    feedback_type = feedback_map.get(body.direction, FeedbackType.interesting)

    # Record feedback
    feedback = UserFeedback(
        user_id=current_user_id(),
        article_id=body.article_id,
        feedback_type=feedback_type,
    )
    db.add(feedback)

    # Adjust user preference for the article's topic
    article_result = await db.execute(
        select(Article)
        .options(selectinload(Article.topics).selectinload(ArticleTopic.topic))
        .where(Article.id == body.article_id)
    )
    article = article_result.scalar_one_or_none()

    if article and article.topics:
        weight_delta = {"right": 0.1, "left": -0.2, "up": 0.3}.get(
            body.direction, 0
        )
        for at in article.topics:
            if at.topic:
                # Upsert preference
                pref_result = await db.execute(
                    select(UserPreference).where(
                        UserPreference.user_id == current_user_id(),
                        UserPreference.topic_id == at.topic_id,
                    )
                )
                pref = pref_result.scalar_one_or_none()
                if pref:
                    pref.weight = max(0.0, pref.weight + weight_delta)
                else:
                    db.add(
                        UserPreference(
                            user_id=current_user_id(),
                            topic_id=at.topic_id,
                            weight=max(0.0, 1.0 + weight_delta),
                        )
                    )
                break  # Only adjust primary topic

    await db.commit()

    logger.info(
        "swipe_recorded",
        article_id=body.article_id,
        direction=body.direction,
    )


@router.get("/discover/topic/{topic_id}", response_model=list[DiscoverCardOut])
async def get_topic_cards(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns 5 cards from a specific topic (triggered by swipe-up).
    """
    from app.services import audience as _audience

    result = await db.execute(
        select(Article)
        .options(
            selectinload(Article.source),
            selectinload(Article.topics).selectinload(ArticleTopic.topic),
        )
        .join(Article.topics)
        .join(Source, Article.source_id == Source.id)
        .where(ArticleTopic.topic_id == topic_id)
        .where(Article.snippet.isnot(None))
        # Gated tiers never arrive as unflagged topic cards — they only ever enter discover via the
        # deck's flagged opt-in sample (which also excludes filing entirely).
        .where(Source.source_type.notin_(list(_audience.gated_source_types())))
        .order_by(Article.published_at.desc().nullslast())
        .limit(5)
    )
    articles = result.scalars().all()

    cards: list[DiscoverCardOut] = []
    for i, article in enumerate(articles):
        topic_name = "General"
        for at in article.topics:
            if at.topic and at.topic_id == topic_id:
                topic_name = at.topic.name
                break

        snippet = article.snippet or ""
        sentences = [s.strip() for s in snippet.split(". ") if s.strip()]
        facts = sentences[:3] if sentences else ["No details available."]

        cards.append(
            DiscoverCardOut(
                id=1000 + i,
                article_id=article.id,
                title=article.title,
                tension_line=article.title,
                facts=facts,
                sources=[article.source.name],
                topic_id=topic_id,
                topic_name=topic_name,
                coherence=0.82,
            )
        )

    return cards


# ── Settings ─────────────────────────────────────────────


def _settings_out(setting) -> UserSettingsOut:
    """Mask every saved key (last-4 only) + surface provider/model prefs. NEVER returns a raw key."""
    if setting is None:
        return UserSettingsOut(has_openai_key=False)
    from app.services.encryption import decrypt_value

    def _last4(enc):
        if not enc:
            return None
        raw = decrypt_value(enc)
        return raw[-4:] if len(raw) >= 4 else "****"

    return UserSettingsOut(
        has_openai_key=bool(setting.openai_api_key_encrypted),
        openai_key_verified=bool(setting.openai_key_verified),  # bool() — transient ORM objs default unset→None
        openai_key_last4=_last4(setting.openai_api_key_encrypted),
        openai_key_verified_at=setting.openai_key_verified_at,
        has_gemini_key=bool(setting.gemini_api_key_encrypted),
        gemini_key_verified=bool(setting.gemini_key_verified),
        gemini_key_last4=_last4(setting.gemini_api_key_encrypted),
        gemini_key_verified_at=setting.gemini_key_verified_at,
        has_anthropic_key=bool(setting.anthropic_api_key_encrypted),
        anthropic_key_verified=bool(setting.anthropic_key_verified),
        anthropic_key_last4=_last4(setting.anthropic_api_key_encrypted),
        anthropic_key_verified_at=setting.anthropic_key_verified_at,
        active_provider=setting.active_provider,
        model_prefs=setting.model_prefs or {},
    )


@router.get("/settings", response_model=UserSettingsOut, dependencies=[Depends(get_current_user)])
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Return current user settings (keys masked)."""
    setting = (
        await db.execute(select(UserSetting).where(UserSetting.user_id == current_user_id()))
    ).scalar_one_or_none()
    return _settings_out(setting)


@router.put("/settings", response_model=UserSettingsOut, dependencies=[Depends(get_current_user)])
async def update_settings(
    body: UserSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update settings: OpenAI key (only when present in the request), active provider, and
    per-provider model overrides. Fields omitted from the request are left untouched (so changing
    the provider never clobbers the saved key)."""
    from fastapi import HTTPException

    setting = (
        await db.execute(select(UserSetting).where(UserSetting.user_id == current_user_id()))
    ).scalar_one_or_none()
    if not setting:
        setting = UserSetting(user_id=current_user_id())
        db.add(setting)

    fields = body.model_fields_set
    if "openai_api_key" in fields:
        from app.services.encryption import encrypt_value

        setting.openai_api_key_encrypted = encrypt_value(body.openai_api_key.strip()) if body.openai_api_key else None
        setting.openai_key_verified = False
        setting.openai_key_verified_at = None
        logger.info("settings_api_key_saved" if body.openai_api_key else "settings_api_key_removed")
    if "active_provider" in fields:
        if body.active_provider not in (None, "openai", "anthropic", "gemini"):
            raise HTTPException(status_code=400, detail="invalid active_provider")
        setting.active_provider = body.active_provider
    if "model_prefs" in fields and body.model_prefs is not None:
        merged = dict(setting.model_prefs or {})
        merged.update(body.model_prefs)  # per-provider merge, never a full clobber
        setting.model_prefs = merged

    await db.commit()
    await db.refresh(setting)
    _invalidate_llm_caches(current_user_id())  # WS-6: provider/model/key change live at once
    return _settings_out(setting)


@router.post("/settings/test-key", response_model=KeyTestResult, dependencies=[Depends(get_current_user)])
async def test_api_key(db: AsyncSession = Depends(get_db)):
    """Test the saved OpenAI API key by listing models."""
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == current_user_id())
    )
    setting = result.scalar_one_or_none()

    if not setting or not setting.openai_api_key_encrypted:
        return KeyTestResult(success=False, error="No API key saved")

    from app.services.encryption import decrypt_value

    raw_key = decrypt_value(setting.openai_api_key_encrypted)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=raw_key)
        models = await client.models.list()
        model_count = len(models.data)

        # Mark as verified
        setting.openai_key_verified = True
        setting.openai_key_verified_at = datetime.now(timezone.utc)
        await db.commit()
        _invalidate_llm_caches(current_user_id())  # WS-6: verified→live now (not after ≤60s TTL)

        logger.info("settings_key_test_success", models=model_count)
        return KeyTestResult(success=True, models_available=model_count)

    except Exception as e:
        setting.openai_key_verified = False
        setting.openai_key_verified_at = None
        await db.commit()

        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            error_msg = "Invalid API key"
        elif "connection" in error_msg.lower():
            error_msg = "Could not connect to OpenAI"
        else:
            error_msg = f"Test failed: {error_msg[:100]}"

        logger.warning("settings_key_test_failed", error=error_msg)
        return KeyTestResult(success=False, error=error_msg)


# ── Saved ──────────────────────────────────────────────


@router.get("/saved", response_model=SavedListResponse, dependencies=[Depends(get_current_user)])
async def get_saved(db: AsyncSession = Depends(get_db)):
    """Return articles saved by the user."""
    result = await db.execute(
        select(UserFeedback)
        .where(
            UserFeedback.user_id == current_user_id(),
            UserFeedback.feedback_type == FeedbackType.save,
        )
        .order_by(UserFeedback.created_at.desc())
    )
    feedbacks = result.scalars().all()

    articles = []
    for fb in feedbacks:
        art_result = await db.execute(
            select(Article)
            .options(selectinload(Article.source))
            .where(Article.id == fb.article_id)
        )
        article = art_result.scalar_one_or_none()
        if not article:
            continue

        # Find cluster_id if article is in a cluster
        cluster_result = await db.execute(
            select(ClusterArticle.cluster_id)
            .where(ClusterArticle.article_id == article.id)
            .limit(1)
        )
        cluster_id = cluster_result.scalar_one_or_none()

        articles.append(
            SavedArticleOut(
                article_id=article.id,
                title=article.title,
                source_name=article.source.name,
                snippet=article.snippet,
                url=article.url,
                cluster_id=cluster_id,
                saved_at=fb.created_at,
            )
        )

    return SavedListResponse(articles=articles, count=len(articles))


@router.delete("/saved/{article_id}", status_code=204, dependencies=[Depends(get_current_user)])
async def unsave_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove saved article by deleting the save feedback."""
    result = await db.execute(
        select(UserFeedback).where(
            UserFeedback.user_id == current_user_id(),
            UserFeedback.article_id == article_id,
            UserFeedback.feedback_type == FeedbackType.save,
        )
    )
    feedback = result.scalar_one_or_none()
    if feedback:
        await db.delete(feedback)
        await db.commit()
        logger.info("article_unsaved", article_id=article_id)


# ── Stats ──────────────────────────────────────────────


@router.get("/stats", response_model=StatsResponse, dependencies=[Depends(get_current_user)])
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Return reading stats for the user."""
    # Articles read = any feedback given
    read_result = await db.execute(
        select(func.count(func.distinct(UserFeedback.article_id))).where(
            UserFeedback.user_id == current_user_id(),
        )
    )
    articles_read = read_result.scalar_one() or 0

    # Stories saved
    saved_result = await db.execute(
        select(func.count()).where(
            UserFeedback.user_id == current_user_id(),
            UserFeedback.feedback_type == FeedbackType.save,
        )
    )
    stories_saved = saved_result.scalar_one() or 0

    # Topics explored = distinct topics from articles the user interacted with
    topics_result = await db.execute(
        select(func.count(func.distinct(ArticleTopic.topic_id)))
        .join(UserFeedback, UserFeedback.article_id == ArticleTopic.article_id)
        .where(UserFeedback.user_id == current_user_id())
    )
    topics_explored = topics_result.scalar_one() or 0

    # WS-5 (#115): impressions + CTR per surface — a bounded LIFETIME aggregate (not a session rate).
    # Both sides count DISTINCT stories per surface so the ratio can't be distorted by the per-DAY
    # impression dedup, a lifetime-pinned `read` row, or un-deduped `interesting` taps (review): a
    # story shown across N days or tapped N times still counts once. clamped to [0,1] as a belt-and-
    # braces against the cluster/article key mismatch. RLS-scoped like the counts above.
    imp_rows = (
        await db.execute(
            select(
                Impression.surface,
                func.count(func.distinct(func.coalesce(Impression.cluster_id, Impression.article_id))),
            )
            .where(Impression.user_id == current_user_id())
            .group_by(Impression.surface)
        )
    ).all()
    click_rows = (
        await db.execute(
            select(UserFeedback.surface, func.count(func.distinct(UserFeedback.article_id)))
            .where(
                UserFeedback.user_id == current_user_id(),
                UserFeedback.surface.isnot(None),
                UserFeedback.feedback_type.in_([FeedbackType.read, FeedbackType.interesting]),
            )
            .group_by(UserFeedback.surface)
        )
    ).all()
    imp_by = {s: n for s, n in imp_rows}
    clicks_by = {s: n for s, n in click_rows}
    # UNION of surfaces so a surface with opens but no logged impressions (e.g. a rail deep-link) is
    # still shown (impressions=0, ctr=0.0) instead of silently dropped.
    surfaces = [
        SurfaceCTR(
            surface=s,
            impressions=imp_by.get(s, 0),
            clicks=clicks_by.get(s, 0),
            ctr=min(1.0, clicks_by.get(s, 0) / imp_by[s]) if imp_by.get(s) else 0.0,
        )
        for s in sorted(set(imp_by) | set(clicks_by))
    ]

    return StatsResponse(
        articles_read=articles_read,
        stories_saved=stories_saved,
        topics_explored=topics_explored,
        surfaces=surfaces,
    )


# ════════════════════════════════════════════════════════════════════
# Enhancement program endpoints (E1 / E3 / E5 / E6 / E7 / E8)
# ════════════════════════════════════════════════════════════════════

async def _user_profession_locale(db: AsyncSession):
    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    return (
        (u.profession if u else None),
        (u.locale if u and u.locale else "IN"),
        (u.persona_version if u and u.persona_version else 1),  # #88 cache key for the LLM classifier
    )


async def _user_depth(db: AsyncSession) -> str:
    """WS-7 (#117): the caller's depth preference (brief/standard/expert) — drives the retrieval
    budget + answer-style suffix across every lens (analysis already did this)."""
    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    return u.depth_pref if u and u.depth_pref else "standard"


async def _user_persona(db: AsyncSession) -> dict:
    """Assemble the full impact persona for the default user. Interests come from the
    user_preferences topic rows (not duplicated onto users)."""
    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    interests = [
        r[0]
        for r in (
            await db.execute(
                select(Topic.name)
                .join(UserPreference, UserPreference.topic_id == Topic.id)
                .where(UserPreference.user_id == current_user_id())
            )
        ).all()
    ]
    return {
        "profession": u.profession if u else None,
        "interests": interests,
        "watchlist": (u.watchlist if u and u.watchlist else []),
        "country": (u.locale if u and u.locale else None),
        "region": (u.region if u else None),
        "depth_pref": (u.depth_pref if u and u.depth_pref else "standard"),
        "persona_version": (u.persona_version if u and u.persona_version else 1),
    }


# ── E3: profile (profession + locale + interests) ──
@router.get("/profile", response_model=ProfileOut, dependencies=[Depends(get_current_user)])
async def get_profile(db: AsyncSession = Depends(get_db)):
    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    prefs = (
        await db.execute(
            select(Topic.name)
            .join(UserPreference, UserPreference.topic_id == Topic.id)
            .where(UserPreference.user_id == current_user_id())
        )
    ).all()
    return ProfileOut(
        profession=u.profession if u else None,
        locale=(u.locale if u and u.locale else "IN"),
        interests=[r[0] for r in prefs],
        watchlist=(u.watchlist if u and u.watchlist else []),
        depth_pref=(u.depth_pref if u and u.depth_pref else "standard"),
        region=(u.region if u else None),
    )


@router.put("/profile", response_model=ProfileOut, dependencies=[Depends(get_current_user)])
async def update_profile(body: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    if not u:
        u = User(id=current_user_id())
        db.add(u)
    if body.profession is not None:
        u.profession = body.profession.strip() or None
    if body.locale is not None:
        u.locale = body.locale.strip() or "IN"
    new_topic_ids: list[int] = []
    canonical_names: set[str] = set()  # the canonical Topic.name for each requested interest
    if body.interests is not None:
        await db.execute(
            UserPreference.__table__.delete().where(
                UserPreference.user_id == current_user_id()
            )
        )
        for raw in body.interests:
            name = raw.strip()
            if not name:
                continue
            topic, created = await _get_or_create_topic(db, name)  # case-insensitive + race-safe
            canonical_names.add(topic.name)
            if created:
                new_topic_ids.append(topic.id)  # only brand-new topics need an article backfill
            await db.execute(
                pg_insert(UserPreference)
                .values(user_id=current_user_id(), topic_id=topic.id, weight=1.0)
                .on_conflict_do_nothing(constraint="uq_user_topic_pref")
            )
        # Unify interests ↔ topic follows: mirror the canonical interest set into topic follows
        # (case-insensitively, so 'AI'/'ai' never fork into two rails), dropping follows no longer wanted.
        existing_follows = (
            await db.execute(
                select(Follow).where(
                    Follow.user_id == current_user_id(), Follow.kind == "topic"
                )
            )
        ).scalars().all()
        have_lower = {ef.value.lower() for ef in existing_follows}
        for nm in canonical_names:
            if nm.lower() not in have_lower:
                db.add(Follow(user_id=current_user_id(), kind="topic", value=nm))
        wanted_lower = {n.lower() for n in canonical_names}
        for ef in existing_follows:
            if ef.value.lower() not in wanted_lower:
                await db.delete(ef)
        from app.services import rails as _rails

        _rails.invalidate(current_user_id())
    if body.watchlist is not None:
        u.watchlist = [w.model_dump() for w in body.watchlist]
    if body.depth_pref is not None:
        u.depth_pref = body.depth_pref.strip() or "standard"
    if body.region is not None:
        u.region = body.region.strip() or None
    # Any profile edit bumps persona_version → lazily invalidates this user's cached impacts.
    u.persona_version = (u.persona_version or 1) + 1
    await db.commit()
    # A freshly-created interest has no tagged articles yet — retroactively tag existing articles in the
    # background (the topic is committed above, so the job's own session sees it) so the interest
    # surfaces content within seconds instead of waiting for the next matching article.
    if new_topic_ids:
        from app.services.fetcher import schedule_topic_backfill

        for tid in new_topic_ids:
            schedule_topic_backfill(tid)
    return await get_profile(db)


@router.post("/profile/backfill-topics", dependencies=[Depends(get_current_user)])
async def backfill_my_topics(db: AsyncSession = Depends(get_db)):
    """Repair + backfill the caller's topics. First RECONCILE legacy topic follows into interests:
    topics followed before unify (e.g. seeded as follows-only) have no UserPreference, so they never
    reach Your Topics / feed rank and the re-follow early-return can't self-heal them — insert the
    missing interest for each. THEN kick a background article→topic backfill for every subscribed topic
    (topics subscribed before the on-subscribe auto-backfill still show 0 articles). Idempotent + deduped."""
    from app.services.fetcher import schedule_topic_backfill

    uid = current_user_id()
    # Reconcile: every kind='topic' Follow should have a matching interest.
    follows = (
        await db.execute(
            select(Follow).where(Follow.user_id == uid, Follow.kind == "topic")
        )
    ).scalars().all()
    reconciled = 0
    for fl in follows:
        topic, _created = await _get_or_create_topic(db, fl.value)
        res = await db.execute(
            pg_insert(UserPreference)
            .values(user_id=uid, topic_id=topic.id, weight=1.0)
            .on_conflict_do_nothing(constraint="uq_user_topic_pref")
        )
        if res.rowcount:
            reconciled += 1
    if reconciled:
        await db.commit()

    topic_ids = (
        await db.execute(select(UserPreference.topic_id).where(UserPreference.user_id == uid))
    ).scalars().all()
    scheduled = sum(1 for tid in topic_ids if schedule_topic_backfill(tid) is not None)
    return {"topics": len(topic_ids), "scheduled": scheduled, "reconciled": reconciled}


# ── E1: per-user Gemini key ──
def _invalidate_llm_caches(uid: int) -> None:
    """WS-6 (#116): drop this user's cached key/provider so a settings write takes effect at once."""
    from app.services import embeddings as _emb
    from app.services import llm as _llm
    _llm.invalidate_user(uid)
    _emb.invalidate_user(uid)


@router.put("/settings/gemini-key", dependencies=[Depends(get_current_user)])
async def set_gemini_key(body: GeminiKeyUpdate, db: AsyncSession = Depends(get_db)):
    from app.services.encryption import encrypt_value

    # ensure the (single) user row exists (prod seeds it; tests use create_all only)
    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    if not u:
        db.add(User(id=current_user_id()))
        await db.flush()

    setting = (
        await db.execute(select(UserSetting).where(UserSetting.user_id == current_user_id()))
    ).scalar_one_or_none()
    if not setting:
        setting = UserSetting(user_id=current_user_id())
        db.add(setting)
    if body.gemini_api_key:
        setting.gemini_api_key_encrypted = encrypt_value(body.gemini_api_key.strip())
        setting.gemini_key_verified = False
        setting.gemini_key_verified_at = None
    else:
        setting.gemini_api_key_encrypted = None
        setting.gemini_key_verified = False
    await db.commit()
    _invalidate_llm_caches(current_user_id())  # WS-6: saved key live at once (with the 60s TTL)
    return {"has_gemini_key": bool(setting.gemini_api_key_encrypted)}


@router.post("/settings/test-gemini-key", response_model=KeyTestResult, dependencies=[Depends(get_current_user)])
async def test_gemini_key(db: AsyncSession = Depends(get_db)):
    from app.services.encryption import decrypt_value

    setting = (
        await db.execute(select(UserSetting).where(UserSetting.user_id == current_user_id()))
    ).scalar_one_or_none()
    if not setting or not setting.gemini_api_key_encrypted:
        return KeyTestResult(success=False, error="No Gemini key saved")
    try:
        key = decrypt_value(setting.gemini_api_key_encrypted)
        import google.generativeai as genai

        genai.configure(api_key=key)
        models = list(genai.list_models())
        setting.gemini_key_verified = True
        setting.gemini_key_verified_at = datetime.now(timezone.utc)
        await db.commit()
        _invalidate_llm_caches(current_user_id())  # WS-6: verified→live now
        return KeyTestResult(success=True, models_available=len(models))
    except Exception as e:  # noqa: BLE001
        return KeyTestResult(success=False, error=str(e)[:200])


@router.put("/settings/anthropic-key", dependencies=[Depends(get_current_user)])
async def set_anthropic_key(body: AnthropicKeyUpdate, db: AsyncSession = Depends(get_db)):
    from app.services.encryption import encrypt_value

    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    if not u:
        db.add(User(id=current_user_id()))
        await db.flush()
    setting = (
        await db.execute(select(UserSetting).where(UserSetting.user_id == current_user_id()))
    ).scalar_one_or_none()
    if not setting:
        setting = UserSetting(user_id=current_user_id())
        db.add(setting)
    if body.anthropic_api_key:
        setting.anthropic_api_key_encrypted = encrypt_value(body.anthropic_api_key.strip())
        setting.anthropic_key_verified = False
        setting.anthropic_key_verified_at = None
    else:
        setting.anthropic_api_key_encrypted = None
        setting.anthropic_key_verified = False
    await db.commit()
    _invalidate_llm_caches(current_user_id())  # WS-6
    return {"has_anthropic_key": bool(setting.anthropic_api_key_encrypted)}


@router.post("/settings/test-anthropic-key", response_model=KeyTestResult, dependencies=[Depends(get_current_user)])
async def test_anthropic_key(db: AsyncSession = Depends(get_db)):
    from app.config import settings
    from app.services.encryption import decrypt_value

    setting = (
        await db.execute(select(UserSetting).where(UserSetting.user_id == current_user_id()))
    ).scalar_one_or_none()
    if not setting or not setting.anthropic_api_key_encrypted:
        return KeyTestResult(success=False, error="No Anthropic key saved")
    try:
        key = decrypt_value(setting.anthropic_api_key_encrypted)
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=key)
        await client.messages.create(
            model=settings.anthropic_model, max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        setting.anthropic_key_verified = True
        setting.anthropic_key_verified_at = datetime.now(timezone.utc)
        await db.commit()
        _invalidate_llm_caches(current_user_id())  # WS-6: verified→live now
        return KeyTestResult(success=True, models_available=1)
    except Exception as e:  # noqa: BLE001
        # REDACT: Anthropic exception text can echo the key / request metadata — never return str(e).
        msg = "Anthropic key test failed"
        try:
            import anthropic as _a

            if isinstance(e, _a.AuthenticationError):
                msg = "Invalid API key"
        except Exception:
            pass
        return KeyTestResult(success=False, error=msg)


# ── E5/E6/E7/E8: cluster lenses ──
@router.get("/clusters/{cluster_id}/analysis", dependencies=[Depends(get_current_user)])
async def cluster_analysis(
    cluster_id: int, lens: str = "key_facts", db: AsyncSession = Depends(get_db)
):
    from fastapi import HTTPException

    from app.services import lenses

    if lens not in ("key_facts", "5ws", "profession"):
        raise HTTPException(status_code=400, detail="invalid lens")
    profession, _, _ = await _user_profession_locale(db)
    # Depth toggle (Brief/Standard/Expert) genuinely changes retrieval budget + answer style.
    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    depth = (u.depth_pref if u and u.depth_pref else "standard")
    return await lenses.analysis(db, cluster_id, lens, profession=profession, depth_pref=depth)


@router.get("/clusters/{cluster_id}/impact", dependencies=[Depends(get_current_user)])
async def cluster_impact(
    cluster_id: int, refresh: int = 0, db: AsyncSession = Depends(get_db)
):
    from app.services import lenses

    persona = await _user_persona(db)
    return await lenses.impact(db, cluster_id, persona, force=bool(refresh))


@router.post("/clusters/{cluster_id}/ask", dependencies=[Depends(get_current_user)])
async def cluster_ask(
    cluster_id: int, body: AskRequest, db: AsyncSession = Depends(get_db)
):
    from fastapi import HTTPException

    from app.services import lenses

    q = (body.question or "").strip()
    if not q or len(q) > 500:
        raise HTTPException(status_code=400, detail="question must be 1-500 characters")
    return await lenses.ask(db, cluster_id, q, depth_pref=await _user_depth(db))


@router.get("/clusters/{cluster_id}/frameworks")
async def cluster_frameworks(cluster_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import lenses

    return await lenses.frameworks(db, cluster_id, depth_pref=await _user_depth(db))


@router.get("/clusters/{cluster_id}/consensus")
async def cluster_consensus(cluster_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import lenses

    return await lenses.consensus(db, cluster_id, depth_pref=await _user_depth(db))


@router.get("/clusters/{cluster_id}/timeline")
async def cluster_timeline(cluster_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import lenses

    return await lenses.timeline(db, cluster_id)


@router.get("/clusters/{cluster_id}/entities", dependencies=[Depends(get_current_user)])
async def cluster_entities_endpoint(cluster_id: int, db: AsyncSession = Depends(get_db)):
    """G1 cast strip: who/what is in this story (salient entities), highest-salience first.
    G2: the owner's followed/read entities rank up when uer_enabled."""
    from app.services import entities

    return await entities.cluster_entities(db, cluster_id, user_id=current_user_id())


@router.get("/entities/{entity_id}/clusters", dependencies=[Depends(get_current_user)])
async def entity_clusters_endpoint(entity_id: int, db: AsyncSession = Depends(get_db)):
    """G1 'appears in' rail: other recent stories touching this entity."""
    from app.services import entities

    return await entities.entity_clusters(db, entity_id)


@router.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)):
    """Resolve the caller from the Firebase ID token (or the default user when unauthenticated).
    The first auth-gated endpoint — makes the seam reachable and lets the frontend confirm sign-in."""
    return {"id": user.id, "firebase_uid": user.firebase_uid, "profession": user.profession}


# ── Wave C: standing follows + "while you were away" digest ──
# Phase 2 · #81: "source" — value is the source id; following bypasses the persona gate.
_FOLLOW_KINDS = {"topic", "entity", "saved_search", "source"}


@router.get("/follows", response_model=list[FollowOut], dependencies=[Depends(get_current_user)])
async def list_follows(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Follow).where(Follow.user_id == current_user_id()).order_by(Follow.id)
        )
    ).scalars().all()
    return [FollowOut.model_validate(f) for f in rows]


async def _get_or_create_topic(db: AsyncSession, name: str) -> tuple[Topic, bool]:
    """Case-INSENSITIVE get-or-create → (topic, created). Returns the canonical existing Topic when the
    name matches case-insensitively (rails match Topic.name via lower(), so the write paths must too, or
    'AI'/'ai' fork into two Topic rows + two rails). Race-safe: a concurrent create is absorbed by
    ON CONFLICT DO NOTHING and we re-SELECT the winner (mirrors the auth.py User-creation guard)."""
    t = (
        await db.execute(select(Topic).where(func.lower(Topic.name) == name.lower()))
    ).scalars().first()
    if t is not None:
        return t, False
    await db.execute(
        pg_insert(Topic).values(name=name).on_conflict_do_nothing(index_elements=["name"])
    )
    t = (
        await db.execute(select(Topic).where(func.lower(Topic.name) == name.lower()))
    ).scalars().first()
    return t, True


async def _sync_topic_follow(db: AsyncSession, name: str) -> "FollowOut":
    """Create/repair a topic follow AND its unified UserPreference interest in ONE transaction,
    idempotently and case-insensitively. Self-heals: re-following a topic that has a Follow but no
    interest (the legacy pre-unify shape) inserts the missing UserPreference instead of no-op'ing at
    the idempotency check. Stores the canonical Topic.name as the follow value so the two never drift."""
    uid = current_user_id()
    topic, _created = await _get_or_create_topic(db, name)
    # Interest (idempotent + race-safe) — the unify half that drives Your Topics / chips / feed rank.
    await db.execute(
        pg_insert(UserPreference)
        .values(user_id=uid, topic_id=topic.id, weight=1.0)
        .on_conflict_do_nothing(constraint="uq_user_topic_pref")
    )
    # Follow (idempotent by case-insensitive value; canonical Topic.name).
    f = (
        await db.execute(
            select(Follow).where(
                Follow.user_id == uid,
                Follow.kind == "topic",
                func.lower(Follow.value) == topic.name.lower(),
            )
        )
    ).scalars().first()
    if f is None:
        f = Follow(user_id=uid, kind="topic", value=topic.name)
        db.add(f)
    await db.commit()
    await db.refresh(f)
    from app.services import rails as _rails

    _rails.invalidate(uid)
    from app.services.fetcher import schedule_topic_backfill

    schedule_topic_backfill(topic.id)
    return FollowOut.model_validate(f)


@router.post("/follows", response_model=FollowOut, status_code=201, dependencies=[Depends(get_current_user)])
async def create_follow(body: FollowCreate, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException

    kind = (body.kind or "").strip().lower()
    value = (body.value or "").strip()
    if kind not in _FOLLOW_KINDS or not value:
        raise HTTPException(status_code=400, detail="invalid kind or empty value")
    # Unify: a topic follow is handled end-to-end (follow + interest, one transaction, self-healing,
    # case-insensitive) so it never falls through the generic idempotent early-return below — which
    # would otherwise skip the interest repair for an already-followed topic.
    if kind == "topic":
        return await _sync_topic_follow(db, value)
    # #81: a source-follow must reference a real source (value = source id) — 404 otherwise, so a
    # typo can't create a dangling opt-in that silently does nothing.
    if kind == "source":
        try:
            _sid = int(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="source follow value must be a source id")
        _stype = (
            await db.execute(select(Source.source_type).where(Source.id == _sid))
        ).scalar_one_or_none()
        if _stype is None:
            raise HTTPException(status_code=404, detail="source not found")
        # A filing source is an exchange firehose — following it would bypass per-company scoping.
        # Watchlist the company instead (which is the only way its filings surface).
        if _stype == SourceType.filing:
            raise HTTPException(
                status_code=400, detail="cannot follow a filing source — watchlist the company instead"
            )
    # Idempotent: a duplicate (user, kind, value) returns the existing row.
    existing = (
        await db.execute(
            select(Follow).where(
                Follow.user_id == current_user_id(),
                Follow.kind == kind,
                Follow.value == value,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return FollowOut.model_validate(existing)
    # WS-2 dedupe (write-side): a saved_search is the least precise rail, so if a more-precise
    # topic/entity follow already covers this value (case-insensitively), return THAT follow instead
    # of minting a redundant row that would render a second identical header. Prefer topic (the exact
    # ArticleTopic match) over entity. Closes the door the interests<->topic-follow unify opened — a
    # chip/onboarding auto-creates the topic follow, and "Follow this search" would re-add it as free
    # text. rails._dedupe_follows still covers rows minted by other paths (read-side complement).
    if kind == "saved_search":
        for _pkind in ("topic", "entity"):
            precise = (
                await db.execute(
                    select(Follow).where(
                        Follow.user_id == current_user_id(),
                        Follow.kind == _pkind,
                        func.lower(Follow.value) == value.lower(),
                    )
                )
            ).scalars().first()
            if precise is not None:
                return FollowOut.model_validate(precise)
    # WS-2 (#112): cap free-text follows so the rails section stays a curated shelf, not a firehose.
    if kind == "saved_search":
        from app.config import settings as _cfg

        count = (
            await db.execute(
                select(func.count()).select_from(Follow).where(
                    Follow.user_id == current_user_id(), Follow.kind == "saved_search"
                )
            )
        ).scalar_one()
        if count >= _cfg.saved_search_cap:
            raise HTTPException(
                status_code=400,
                detail=f"you follow {_cfg.saved_search_cap} topics — unfollow one first",
            )
    f = Follow(
        user_id=current_user_id(), kind=kind, value=value,
        entity_id=(body.entity_id if kind == "entity" else None),
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    from app.services import rails as _rails
    _rails.invalidate(current_user_id())  # WS-2: a new follow changes the rails payload
    if kind == "entity":
        from app.config import settings
        from app.services import entities

        if f.entity_id is not None:
            # G2: trustworthy entity id from the tapped chip → persist + seed the relevance overlay.
            await entities.bump_relevance(
                db, current_user_id(), f.entity_id, source="follow", weight=settings.uer_follow_weight
            )
            await db.commit()
        else:
            # String/typed path: resolve_existing is kind-blind (best-effort) — but a typed entity
            # follow is still an explicit signal, so seed relevance when it resolves to a node. The
            # follow row keeps entity_id NULL (only the chip path persists the trustworthy id).
            eid = await entities.resolve_existing(db, value)
            if eid is not None:
                await entities.bump_relevance(
                    db, current_user_id(), eid, source="follow", weight=settings.uer_follow_weight
                )
                await db.commit()
            logger.info("entity_follow_resolved", value=value, entity_id=eid)
    return FollowOut.model_validate(f)


@router.delete("/follows/{follow_id}", status_code=204, dependencies=[Depends(get_current_user)])
async def delete_follow(follow_id: int, db: AsyncSession = Depends(get_db)):
    f = (
        await db.execute(
            select(Follow).where(
                Follow.id == follow_id, Follow.user_id == current_user_id()
            )
        )
    ).scalar_one_or_none()
    if f is not None:
        if f.kind == "topic":
            # Unify: unfollowing a topic also drops the matching interest. Case-insensitive resolve so
            # a legacy follow whose value differs in case from the canonical Topic.name still matches.
            t = (
                await db.execute(select(Topic).where(func.lower(Topic.name) == f.value.lower()))
            ).scalars().first()
            if t is not None:
                await db.execute(
                    UserPreference.__table__.delete().where(
                        UserPreference.user_id == current_user_id(),
                        UserPreference.topic_id == t.id,
                    )
                )
        await db.delete(f)
        await db.commit()
        from app.services import rails as _rails
        _rails.invalidate(current_user_id())


@router.get("/follows/rails", dependencies=[Depends(get_current_user)])
async def follows_rails(db: AsyncSession = Depends(get_db)):
    """WS-2 (#112): the "News You Follow" section — one rail per rail-able follow (saved_search /
    topic / entity; source follows excluded), 72h-windowed, with a per-rail badge new_count. ONE
    request; the server loops the follows (60s cached). A failing follow drops its rail, never the
    section."""
    from app.services import rails as _rails

    return {"rails": await _rails.rails_for_user(db, current_user_id())}


@router.post("/follows/{follow_id}/seen", status_code=204, dependencies=[Depends(get_current_user)])
async def mark_follow_seen(follow_id: int, db: AsyncSession = Depends(get_db)):
    """WS-2 (#112): clears a rail's badge — sets follows.last_viewed_at=now for THIS follow only
    (tapping a rail story or its 'see all'). Per-follow, so viewing one rail never clears another,
    and (unlike the global User.last_seen_at) reading the digest never clears rail badges."""
    f = (
        await db.execute(
            select(Follow).where(Follow.id == follow_id, Follow.user_id == current_user_id())
        )
    ).scalar_one_or_none()
    if f is not None:
        f.last_viewed_at = datetime.now(timezone.utc)
        await db.commit()
        from app.services import rails as _rails
        _rails.invalidate(current_user_id())


@router.get("/digest", response_model=DigestResponse, dependencies=[Depends(get_current_user)])
async def get_digest(db: AsyncSession = Depends(get_db)):
    """In-app 'while you were away' — clusters formed since the last visit, with their cached
    WIIFM headline (no new LLM calls). Marks the visit as seen."""
    from datetime import timedelta

    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    since = u.last_seen_at if (u and u.last_seen_at) else (now - timedelta(hours=24))
    # Persona-gate the digest exactly like the briefing — officials/research form SINGLETON clusters,
    # so an ungated 3-newest-clusters window would put RBI circulars on every user's home screen.
    from sqlalchemy import exists as _sa_exists

    from app.config import settings as app_settings
    from app.services import audience as _audience
    _profession, _, _pv = await _user_profession_locale(db)
    _tags = await _audience.resolve_tags(_profession, user_id=current_user_id(), persona_version=_pv)
    _followed = await _audience.followed_source_ids(db, current_user_id())
    _allowed = _audience.allowed_source_ids(
        _tags, floor=app_settings.credibility_briefing_floor, followed_source_ids=_followed
    )
    _visible = _sa_exists().where(
        ClusterArticle.cluster_id == StoryCluster.id,
        ClusterArticle.article_id == Article.id,
        Article.source_id.in_(_allowed),
    )
    rows = (
        await db.execute(
            select(StoryCluster)
            .where(StoryCluster.created_at > since, _visible)
            .order_by(StoryCluster.created_at.desc())
            .limit(3)
        )
    ).scalars().all()
    items = [
        DigestItem(
            cluster_id=c.id, title=c.title,
            headline=_extract_impact_headline(c.impact_json),
        )
        for c in rows
    ]
    if u is not None:
        u.last_seen_at = now
        await db.commit()
    return DigestResponse(count=len(items), since=since.isoformat(), items=items)


_GEOPOLITICS_TOPIC_TERMS = (
    "world", "geopolitics", "international", "politics", "conflict", "defense",
)


@router.get("/clusters/{cluster_id}/strategic")
async def cluster_strategic(cluster_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import lenses

    # E7: topic-gate. Only offer the strategic/game-theory lens for geopolitics-ish
    # stories. Load the cluster's topic names (articles -> ArticleTopic -> Topic).
    topic_rows = (
        await db.execute(
            select(Topic.name)
            .join(ArticleTopic, ArticleTopic.topic_id == Topic.id)
            .join(ClusterArticle, ClusterArticle.article_id == ArticleTopic.article_id)
            .where(ClusterArticle.cluster_id == cluster_id)
        )
    ).all()
    topic_names = [r[0].lower() for r in topic_rows if r[0]]
    is_geopolitical = any(
        term in name for name in topic_names for term in _GEOPOLITICS_TOPIC_TERMS
    )
    if not is_geopolitical:
        return {"unavailable": True, "reason": "not_offered_for_topic"}

    return await lenses.strategic(db, cluster_id, depth_pref=await _user_depth(db))


@router.get("/clusters/{cluster_id}/trivia")
async def cluster_trivia(
    cluster_id: int, difficulty: str = "medium", db: AsyncSession = Depends(get_db)
):
    from fastapi import HTTPException

    from app.services import lenses

    if difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="invalid difficulty")
    return await lenses.trivia(db, cluster_id, difficulty, depth_pref=await _user_depth(db))


@router.get("/trivia/daily")
async def trivia_daily(
    topic: str = "world news", difficulty: str = "medium",
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    from app.services import llm

    if difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="invalid difficulty")
    prompt = (
        f"Write 3 {difficulty}-difficulty multiple-choice quiz questions about recent "
        f"developments in {topic}. Each has exactly 4 options, one correct. "
        'Respond ONLY as JSON: {"questions": [{"question": "...", '
        '"options": ["a","b","c","d"], "answer_index": 0, "explanation": "...", '
        '"difficulty": "' + difficulty + '"}]}'
    )
    try:
        return await llm.generate(prompt, schema={"questions": []})
    except llm.LLMUnavailable:
        return {"unavailable": True, "reason": "no_llm_key"}
    except Exception as e:  # noqa: BLE001 — graceful degradation, never 500
        # Log the provider error — a silent swallow here hid the retired-model 404 in prod
        # (the response said only "llm_error" and the root cause had to be inferred).
        logger.warning("trivia_daily_llm_failed", error=str(e))
        return {"unavailable": True, "reason": "llm_error"}


# ── E2: admin sources ──
@router.get("/admin/sources", dependencies=[Depends(get_current_user)])
async def list_sources(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Source).order_by(Source.name))).scalars().all()
    return [
        {
            "id": s.id, "name": s.name, "url": s.url, "rss_url": s.rss_url,
            "region": s.region, "category": s.category,
            "is_paywalled": s.is_paywalled,
            "source_type": s.source_type.value if s.source_type else None,
        }
        for s in rows
    ]


# Auth-gated (was completely open — anyone could upsert prod sources). With AUTH_REQUIRED=false the
# dependency still resolves the default user (single-user mode); it starts rejecting the moment
# AUTH_REQUIRED=true, without another code change.
@router.post("/admin/sources", dependencies=[Depends(get_current_user)])
async def create_source(body: dict, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    from sqlalchemy import or_

    name = (body.get("name") or "").strip()
    url = (body.get("url") or "").strip()
    if not name or not url:
        raise HTTPException(status_code=400, detail="name and url are required")
    rss_url = (body.get("rss_url") or "").strip() or None

    # Gated tiers are admission-controlled: no vetting score, no publish.
    source_type = body.get("source_type", "other")
    credibility_score = body.get("credibility_score")
    if source_type in ("research", "expert", "official", "filing") and credibility_score is None:
        raise HTTPException(
            status_code=400,
            detail="research/expert sources require a credibility_score",
        )
    # Scores are a 0-100 scale; a value outside it would break the ×[0.9,1.1] feed-rank bound
    # (the "credibility can never drown fresher news" guarantee). Reject at the write boundary.
    if credibility_score is not None and not (0 <= credibility_score <= 100):
        raise HTTPException(status_code=400, detail="credibility_score must be between 0 and 100")

    # Audience contract at the write boundary: an official with audience=NULL would be visible to
    # EVERYONE (allowed_source_ids treats NULL as "general") — defeating the tier. A filing is
    # ALWAYS watchlist/follow-only: force audience=[] regardless of what the caller sent.
    audience_field = body.get("audience")
    if source_type == "official" and not audience_field:
        raise HTTPException(status_code=400, detail="official sources require a non-empty audience")
    if source_type == "filing":
        audience_field = []

    # UPSERT: if a source with the same url OR rss_url exists, update it in place.
    match_clauses = [Source.url == url]
    if rss_url:
        match_clauses.append(Source.rss_url == rss_url)
    existing = (
        await db.execute(select(Source).where(or_(*match_clauses)))
    ).scalar_one_or_none()
    if existing is not None:
        existing.name = name
        existing.region = body.get("region", existing.region)
        existing.category = body.get("category", existing.category)
        await db.commit()
        return {"id": existing.id, "name": existing.name, "updated": True}

    # An admin publishing through this endpoint IS the human review — stamp it so the 10-min
    # sources.json re-upsert never clobbers the curated score (see fetcher._upsert_sources).
    credibility_meta = body.get("credibility_meta") or {}
    if credibility_score is not None:
        credibility_meta = {**credibility_meta, "reviewed_by": "admin"}

    s = Source(
        name=name, url=url, rss_url=rss_url,
        is_paywalled=bool(body.get("is_paywalled", False)),
        source_type=source_type,
        region=body.get("region", "global"), category=body.get("category"),
        author_name=body.get("author_name"),
        credibility_score=credibility_score,
        credibility_meta=credibility_meta or None,
        audience=audience_field,
        is_preprint=bool(body.get("is_preprint", False)),
        per_fetch_cap=body.get("per_fetch_cap"),
    )
    db.add(s)
    await db.commit()
    return {"id": s.id, "name": s.name, "updated": False}


@router.put("/admin/sources/{source_id}/credibility", dependencies=[Depends(get_current_user)])
async def apply_credibility(source_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    """Phase 3 · #85 — the human half of the credibility-review loop. An admin applies a (proposed
    or corrected) score; we stamp credibility_meta.reviewed_by="admin", which locks the row against
    the 10-minute seed re-upsert (fetcher._upsert_sources), so a manual correction is never silently
    clobbered by sources.json."""
    from fastapi import HTTPException

    score = body.get("credibility_score")
    if score is None or not (0 <= score <= 100):
        raise HTTPException(status_code=400, detail="credibility_score must be between 0 and 100")

    source = (await db.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")

    # Merge into existing meta so the LLM proposal / rationale / affiliation history is preserved.
    meta = dict(source.credibility_meta or {})
    meta["reviewed_by"] = "admin"
    meta["applied_score"] = score
    if body.get("rationale"):
        meta["rationale"] = body["rationale"]
    source.credibility_score = score
    source.credibility_meta = meta
    await db.commit()
    return {"id": source.id, "credibility_score": score, "reviewed_by": "admin"}


@router.get("/admin/breadth", dependencies=[Depends(get_current_user)])
async def admin_breadth(days: int = Query(None, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    """#97 — source-diversity / coverage / staleness metrics for the corpus. Aggregate SQL, no N+1."""
    from datetime import datetime, timedelta, timezone

    from app.config import settings as app_settings

    from app.services import audience as _audience

    window = days or app_settings.breadth_stale_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)
    _gated = list(_audience.gated_source_types())

    by_type_rows = (await db.execute(
        select(Source.source_type, func.count()).group_by(Source.source_type))).all()
    by_type = {(st.value if st else "unknown"): n for st, n in by_type_rows}
    by_region_rows = (await db.execute(
        select(Source.region, func.count()).group_by(Source.region))).all()
    by_region = {(r or "unknown"): n for r, n in by_region_rows}

    total_sources = (await db.execute(select(func.count()).select_from(Source))).scalar_one()
    gated_sources = (await db.execute(
        select(func.count()).select_from(Source).where(Source.source_type.in_(_gated)))).scalar_one()
    total_articles = (await db.execute(select(func.count()).select_from(Article))).scalar_one()
    gated_articles = (await db.execute(
        select(func.count()).select_from(Article).join(Source, Source.id == Article.source_id)
        .where(Source.source_type.in_(_gated)))).scalar_one()

    def _pct(a, b):
        return round(100.0 * a / b, 1) if b else 0.0

    # One aggregate pass: per-source article count + latest fetch → leaderboard, zero-count, staleness.
    per_source = (await db.execute(
        select(Source.id, Source.name, func.count(Article.id), func.max(Article.fetched_at))
        .outerjoin(Article, Article.source_id == Source.id)
        .group_by(Source.id, Source.name))).all()
    ranked = sorted(per_source, key=lambda r: r[2], reverse=True)
    top = [{"source_id": sid, "name": name, "count": cnt} for sid, name, cnt, _ in ranked[:20]]
    zero_article_sources = sum(1 for _, _, cnt, _ in per_source if cnt == 0)
    stale_sources = [
        {"source_id": sid, "name": name, "last_article_at": last.isoformat() if last else None}
        for sid, name, cnt, last in per_source
        if cnt > 0 and last is not None and last < cutoff
    ]

    per_topic = (await db.execute(
        select(Topic.id, Topic.name, func.count(ArticleTopic.id))
        .join(ArticleTopic, ArticleTopic.topic_id == Topic.id)
        .group_by(Topic.id, Topic.name).order_by(func.count(ArticleTopic.id).desc()))).all()
    articles_per_topic = [{"topic_id": tid, "name": name, "count": cnt} for tid, name, cnt in per_topic]

    return {
        "days": window,
        "sources": {"total": total_sources, "gated": gated_sources,
                    "by_type": by_type, "by_region": by_region},
        "articles": {"total": total_articles, "gated": gated_articles},
        "gated_share": {"sources_pct": _pct(gated_sources, total_sources),
                        "articles_pct": _pct(gated_articles, total_articles)},
        "articles_per_source": {"top": top, "zero_article_sources": zero_article_sources},
        "articles_per_topic": articles_per_topic,
        "stale_sources": stale_sources,
    }


async def _sse_stream():
    """#101: yield hub events as SSE frames. On client disconnect, sse-starlette cancels this
    generator → the hub subscription's finally unregisters the queue (no leak)."""
    import json as _json

    from app.services import events as _events
    async for evt in _events.hub.subscribe():
        yield {"event": evt["type"], "data": _json.dumps(evt["data"])}


@router.get("/events")
async def sse_events():
    """Unauthenticated global signal channel (ids/counts only, never per-user data) — a client uses
    it to know WHEN to re-fetch, then hits the normal (authenticated) endpoints for the content."""
    from sse_starlette.sse import EventSourceResponse

    return EventSourceResponse(_sse_stream())


# ── E4: hybrid search (semantic + keyword; keyword ranks above semantic-only) ──
@router.get("/search", dependencies=[Depends(get_current_user)])
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    query_str = q.strip()
    if not query_str:
        raise HTTPException(status_code=400, detail="empty query")

    results: dict[int, dict] = {}

    # Semantic (pgvector NN) — lower priority than exact keyword.
    # Use the cached query-embedding helper to avoid re-embedding repeated queries.
    from app.services.embeddings import embed_query_cached, vector_literal

    try:
        emb = await embed_query_cached(query_str)
    except Exception:  # noqa: BLE001
        emb = None
    if emb is not None:
        rows = (
            await db.execute(
                text(
                    "SELECT id FROM articles WHERE embedding IS NOT NULL "
                    "ORDER BY embedding <=> :v LIMIT :k"
                ),
                {"v": vector_literal(emb), "k": limit},
            )
        ).all()
        for i, (aid,) in enumerate(rows):
            results[aid] = {"id": aid, "matched_on": "meaning", "rank": 100 + i}

    # Keyword (exact substring) — promote to the top.
    kw_rows = (
        await db.execute(
            select(Article.id).where(Article.title.ilike(f"%{query_str}%")).limit(limit)
        )
    ).all()
    for (aid,) in kw_rows:
        if aid in results:
            results[aid]["matched_on"] = "topic+meaning"
            results[aid]["rank"] = 0
        else:
            results[aid] = {"id": aid, "matched_on": "topic", "rank": 0}

    ids = list(results.keys())
    if not ids:
        return {"query": query_str, "results": []}

    arts = (
        await db.execute(
            select(Article).options(selectinload(Article.source)).where(Article.id.in_(ids))
        )
    ).scalars().all()
    art_map = {a.id: a for a in arts}
    ca = (
        await db.execute(
            select(ClusterArticle.article_id, ClusterArticle.cluster_id).where(
                ClusterArticle.article_id.in_(ids)
            )
        )
    ).all()
    art_to_cluster = {aid: cid for aid, cid in ca}

    # Group/dedup by cluster: keep only the highest-ranked (lowest rank value)
    # article per cluster_id. Articles with no cluster stay as individual results.
    out = []
    seen_clusters: set[int] = set()
    for aid, meta in sorted(results.items(), key=lambda kv: kv[1]["rank"]):
        a = art_map.get(aid)
        if not a:
            continue
        cluster_id = art_to_cluster.get(a.id)
        if cluster_id is not None:
            if cluster_id in seen_clusters:
                continue
            seen_clusters.add(cluster_id)
        out.append({
            "id": a.id, "title": a.title, "snippet": a.snippet, "url": a.url,
            "source": SourceOut.model_validate(a.source).model_dump(),
            "cluster_id": cluster_id,
            "matched_on": meta["matched_on"],
            "_rank": meta["rank"],
        })

    # G2: within-tier relevance boost. Dedup ran on the ORIGINAL rank (so the representative article
    # per cluster is unchanged); now nudge whole clusters the user has affinity for. The boost is
    # capped well below the 100-point keyword/semantic tier gap, so a boosted semantic result can
    # outrank an unboosted semantic one but NEVER crosses a keyword result (rank 0). Off → no reorder.
    from app.config import settings as app_settings

    if app_settings.uer_enabled:
        from app.services import entities

        cl_ids = [o["cluster_id"] for o in out if o["cluster_id"] is not None]
        scores = await entities.score_clusters_relevance(db, cl_ids, current_user_id())

        def _effective_rank(o):
            rel = min(1.0, scores.get(o["cluster_id"], 0.0))
            boost = (app_settings.uer_search_rerank_boost * rel
                     if rel >= app_settings.uer_search_relevance_threshold else 0.0)
            return o["_rank"] - boost

        out.sort(key=_effective_rank)  # stable: ties keep dedup order

    for o in out:
        o.pop("_rank", None)
    return {"query": query_str, "results": out}
