import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
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
    Source,
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
    FeedbackCreate,
    FeedbackOut,
    FeedResponse,
    GeminiKeyUpdate,
    HealthResponse,
    KeyTestResult,
    ProfileOut,
    ProfileUpdate,
    SavedArticleOut,
    SavedListResponse,
    SourceOut,
    StatsResponse,
    SwipeRequest,
    TopicOut,
    TopicListResponse,
    UserSettingsOut,
    UserSettingsUpdate,
)

logger = structlog.get_logger()
router = APIRouter()


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


@router.get("/feed", response_model=FeedResponse, dependencies=[Depends(get_current_user)])
async def get_feed(
    topic: int | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page

    query = (
        select(Article)
        .options(selectinload(Article.source))
        .order_by(Article.published_at.desc().nullslast())
    )

    if topic:
        query = query.join(Article.topics).where(
            Article.topics.any(topic_id=topic)
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Get paginated results
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

    article_outs = []
    for a in articles:
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
    from app.config import settings as app_settings
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

    return FeedResponse(
        articles=article_outs,
        total=total,
        page=page,
        per_page=per_page,
        explore_ratio=explore_ratio,
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

    # On-demand summary generation if batch missed this cluster
    if not cluster.summary:
        try:
            from app.services.summarizer import summarize_cluster
            summary_result = await summarize_cluster(cluster.id)
            if summary_result:
                cluster.summary, cluster.coherence = summary_result
        except Exception as e:
            logger.warning("on_demand_summary_failed", cluster_id=cluster.id, error=str(e))

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

    return ClusterDetailOut(
        id=cluster.id,
        title=cluster.title,
        summary=cluster.summary,
        created_at=cluster.created_at,
        coherence=getattr(cluster, "coherence", None),  # real coherence; None when not yet computed
        sources=source_cards,
    )


@router.get("/topics", response_model=TopicListResponse)
async def get_topics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Topic).order_by(Topic.name))
    topics = result.scalars().all()

    topic_outs = []
    for t in topics:
        topic_outs.append(
            TopicOut(
                id=t.id,
                name=t.name,
                article_count=0,
                is_explore=False,
            )
        )

    # For MVP: all topics go in your_topics, explore and trending are empty
    return TopicListResponse(
        your_topics=topic_outs,
        explore_topics=[],
        trending_topics=[],
    )


@router.post("/feedback", response_model=FeedbackOut, status_code=201, dependencies=[Depends(get_current_user)])
async def create_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    feedback = UserFeedback(
        user_id=current_user_id(),
        article_id=body.article_id,
        feedback_type=body.feedback_type,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    logger.info(
        "feedback_created",
        article_id=body.article_id,
        feedback_type=body.feedback_type.value,
    )

    return FeedbackOut.model_validate(feedback)


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

    # Get recent clusters with their articles + sources + topics
    result = await db.execute(
        select(StoryCluster)
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

    # Track stories with their preference weights for explore/exploit sorting
    stories: list[BriefingStory] = []
    story_weights: dict[int, float] = {}  # cluster_id -> pref_weight

    for cluster in clusters:
        # Count unique sources and gather metadata
        source_names = set()
        first_snippet = None
        category = "General"
        topic_id = None
        cluster_article_ids = []
        for ca in cluster.articles:
            source_names.add(ca.article.source.name)
            cluster_article_ids.append(ca.article.id)
            if first_snippet is None and ca.article.snippet:
                first_snippet = ca.article.snippet
            if category == "General" and ca.article.topics:
                for at in ca.article.topics:
                    if at.topic:
                        category = at.topic.name
                        topic_id = at.topic_id
                        break

        # Use real summary or on-demand generate
        summary = cluster.summary
        coherence = cluster.coherence
        if not summary:
            try:
                from app.services.summarizer import summarize_cluster
                sr = await summarize_cluster(cluster.id)
                if sr:
                    summary, coherence = sr
            except Exception as e:
                logger.warning("briefing_summary_failed", cluster_id=cluster.id, error=str(e))

        if not summary:
            summary = first_snippet or "No summary available."
            sentences = summary.split(". ")
            if len(sentences) > 2:
                summary = ". ".join(sentences[:2]) + "."

        # Dynamic coherence from source count if not set
        if coherence is None:
            sc = len(source_names)
            if sc >= 5:
                coherence = 0.95
            elif sc >= 3:
                coherence = 0.85
            elif sc >= 2:
                coherence = 0.75
            else:
                coherence = 0.65

        # Check if any article in this cluster has been read
        is_read = any(aid in read_article_ids for aid in cluster_article_ids)

        # Track preference weight for explore/exploit sorting
        pref_weight = prefs.get(topic_id, 0.0) if topic_id else 0.0
        story_weights[cluster.id] = pref_weight

        # E6: best-effort WIIFM headline from ALREADY-cached impact_json (no LLM calls).
        impact_headline = _extract_impact_headline(cluster.impact_json)

        stories.append(
            BriefingStory(
                title=cluster.title,
                summary=summary,
                cluster_id=cluster.id,
                category=category,
                source_count=len(source_names),
                coherence=coherence,
                is_read=is_read,
                impact_headline=impact_headline,
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

    # Fallback: if no clusters, build briefing from recent articles
    if not stories:
        article_result = await db.execute(
            select(Article)
            .options(selectinload(Article.source))
            .where(Article.snippet.isnot(None))
            .order_by(Article.published_at.desc().nullslast())
            .limit(8)
        )
        articles = article_result.scalars().all()

        source_categories = {
            "BBC News": "World",
            "Al Jazeera": "World",
            "NPR News": "World",
            "Reuters - World": "World",
            "TechCrunch": "Tech",
            "Ars Technica": "Tech",
            "The Verge": "Tech",
            "Hacker News": "Tech",
            "Nature News": "Science",
            "Wall Street Journal": "Business",
        }

        for a in articles:
            snippet = a.snippet or ""
            sentences = snippet.split(". ")
            summary = ". ".join(sentences[:2]) + "." if len(sentences) > 1 else snippet
            category = source_categories.get(a.source.name, "General")
            is_read = a.id in read_article_ids

            stories.append(
                BriefingStory(
                    title=a.title,
                    summary=summary,
                    cluster_id=a.id,
                    category=category,
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
    result = await db.execute(
        select(Article)
        .options(
            selectinload(Article.source),
            selectinload(Article.topics).selectinload(ArticleTopic.topic),
        )
        .where(Article.snippet.isnot(None))
        .order_by(func.random())
        .limit(25)
    )
    articles = result.scalars().all()

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

        cards.append(
            DiscoverCardOut(
                id=i + 1,
                article_id=article.id,
                title=article.title,
                tension_line=article.title,  # MVP: title as tension line
                facts=facts,
                sources=[article.source.name],
                topic_id=topic_id,
                topic_name=topic_name,
                coherence=0.82,  # placeholder
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
    result = await db.execute(
        select(Article)
        .options(
            selectinload(Article.source),
            selectinload(Article.topics).selectinload(ArticleTopic.topic),
        )
        .join(Article.topics)
        .where(ArticleTopic.topic_id == topic_id)
        .where(Article.snippet.isnot(None))
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


@router.get("/settings", response_model=UserSettingsOut, dependencies=[Depends(get_current_user)])
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Return current user settings (API key masked)."""
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == current_user_id())
    )
    setting = result.scalar_one_or_none()

    if not setting:
        return UserSettingsOut(has_openai_key=False, has_gemini_key=False)

    from app.services.encryption import decrypt_value

    openai_last4 = None
    if setting.openai_api_key_encrypted:
        raw_openai = decrypt_value(setting.openai_api_key_encrypted)
        openai_last4 = raw_openai[-4:] if len(raw_openai) >= 4 else "****"

    gemini_last4 = None
    if setting.gemini_api_key_encrypted:
        raw_gemini = decrypt_value(setting.gemini_api_key_encrypted)
        gemini_last4 = raw_gemini[-4:] if len(raw_gemini) >= 4 else "****"

    return UserSettingsOut(
        has_openai_key=bool(setting.openai_api_key_encrypted),
        openai_key_verified=setting.openai_key_verified,
        openai_key_last4=openai_last4,
        openai_key_verified_at=setting.openai_key_verified_at,
        has_gemini_key=bool(setting.gemini_api_key_encrypted),
        gemini_key_verified=setting.gemini_key_verified,
        gemini_key_last4=gemini_last4,
        gemini_key_verified_at=setting.gemini_key_verified_at,
    )


@router.put("/settings", response_model=UserSettingsOut, dependencies=[Depends(get_current_user)])
async def update_settings(
    body: UserSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Save or remove the OpenAI API key."""
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == current_user_id())
    )
    setting = result.scalar_one_or_none()

    if not setting:
        setting = UserSetting(user_id=current_user_id())
        db.add(setting)

    if body.openai_api_key:
        from app.services.encryption import encrypt_value

        setting.openai_api_key_encrypted = encrypt_value(body.openai_api_key)
        setting.openai_key_verified = False
        setting.openai_key_verified_at = None
        logger.info("settings_api_key_saved")
    else:
        setting.openai_api_key_encrypted = None
        setting.openai_key_verified = False
        setting.openai_key_verified_at = None
        logger.info("settings_api_key_removed")

    await db.commit()
    await db.refresh(setting)

    if not setting.openai_api_key_encrypted:
        return UserSettingsOut(has_openai_key=False)

    from app.services.encryption import decrypt_value

    raw_key = decrypt_value(setting.openai_api_key_encrypted)
    last4 = raw_key[-4:] if len(raw_key) >= 4 else "****"

    return UserSettingsOut(
        has_openai_key=True,
        openai_key_verified=setting.openai_key_verified,
        openai_key_last4=last4,
    )


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

    return StatsResponse(
        articles_read=articles_read,
        stories_saved=stories_saved,
        topics_explored=topics_explored,
    )


# ════════════════════════════════════════════════════════════════════
# Enhancement program endpoints (E1 / E3 / E5 / E6 / E7 / E8)
# ════════════════════════════════════════════════════════════════════

async def _user_profession_locale(db: AsyncSession):
    u = (
        await db.execute(select(User).where(User.id == current_user_id()))
    ).scalar_one_or_none()
    return (u.profession if u else None), (u.locale if u and u.locale else "IN")


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
            topic = (
                await db.execute(select(Topic).where(Topic.name == name))
            ).scalar_one_or_none()
            if not topic:
                topic = Topic(name=name)
                db.add(topic)
                await db.flush()
            db.add(
                UserPreference(user_id=current_user_id(), topic_id=topic.id, weight=1.0)
            )
    if body.watchlist is not None:
        u.watchlist = [w.model_dump() for w in body.watchlist]
    if body.depth_pref is not None:
        u.depth_pref = body.depth_pref.strip() or "standard"
    if body.region is not None:
        u.region = body.region.strip() or None
    # Any profile edit bumps persona_version → lazily invalidates this user's cached impacts.
    u.persona_version = (u.persona_version or 1) + 1
    await db.commit()
    return await get_profile(db)


# ── E1: per-user Gemini key ──
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
        return KeyTestResult(success=True, models_available=len(models))
    except Exception as e:  # noqa: BLE001
        return KeyTestResult(success=False, error=str(e)[:200])


# ── E5/E6/E7/E8: cluster lenses ──
@router.get("/clusters/{cluster_id}/analysis", dependencies=[Depends(get_current_user)])
async def cluster_analysis(
    cluster_id: int, lens: str = "key_facts", db: AsyncSession = Depends(get_db)
):
    from fastapi import HTTPException

    from app.services import lenses

    if lens not in ("key_facts", "5ws", "profession"):
        raise HTTPException(status_code=400, detail="invalid lens")
    profession, _ = await _user_profession_locale(db)
    return await lenses.analysis(db, cluster_id, lens, profession=profession)


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
    return await lenses.ask(db, cluster_id, q)


@router.get("/clusters/{cluster_id}/frameworks")
async def cluster_frameworks(cluster_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import lenses

    return await lenses.frameworks(db, cluster_id)


@router.get("/clusters/{cluster_id}/consensus")
async def cluster_consensus(cluster_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import lenses

    return await lenses.consensus(db, cluster_id)


@router.get("/clusters/{cluster_id}/timeline")
async def cluster_timeline(cluster_id: int, db: AsyncSession = Depends(get_db)):
    from app.services import lenses

    return await lenses.timeline(db, cluster_id)


@router.get("/clusters/{cluster_id}/entities", dependencies=[Depends(get_current_user)])
async def cluster_entities_endpoint(cluster_id: int, db: AsyncSession = Depends(get_db)):
    """G1 cast strip: who/what is in this story (salient entities), highest-salience first."""
    from app.services import entities

    return await entities.cluster_entities(db, cluster_id)


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
_FOLLOW_KINDS = {"topic", "entity", "saved_search"}


@router.get("/follows", response_model=list[FollowOut], dependencies=[Depends(get_current_user)])
async def list_follows(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Follow).where(Follow.user_id == current_user_id()).order_by(Follow.id)
        )
    ).scalars().all()
    return [FollowOut.model_validate(f) for f in rows]


@router.post("/follows", response_model=FollowOut, status_code=201, dependencies=[Depends(get_current_user)])
async def create_follow(body: FollowCreate, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException

    kind = (body.kind or "").strip().lower()
    value = (body.value or "").strip()
    if kind not in _FOLLOW_KINDS or not value:
        raise HTTPException(status_code=400, detail="invalid kind or empty value")
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
    f = Follow(user_id=current_user_id(), kind=kind, value=value)
    db.add(f)
    await db.commit()
    await db.refresh(f)
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
        await db.delete(f)
        await db.commit()


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
    rows = (
        await db.execute(
            select(StoryCluster)
            .where(StoryCluster.created_at > since)
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

    return await lenses.strategic(db, cluster_id)


@router.get("/clusters/{cluster_id}/trivia")
async def cluster_trivia(
    cluster_id: int, difficulty: str = "medium", db: AsyncSession = Depends(get_db)
):
    from fastapi import HTTPException

    from app.services import lenses

    if difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="invalid difficulty")
    return await lenses.trivia(db, cluster_id, difficulty)


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
    except Exception:  # noqa: BLE001 — graceful degradation, never 500
        return {"unavailable": True, "reason": "llm_error"}


# ── E2: admin sources ──
@router.get("/admin/sources")
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


@router.post("/admin/sources")
async def create_source(body: dict, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    from sqlalchemy import or_

    name = (body.get("name") or "").strip()
    url = (body.get("url") or "").strip()
    if not name or not url:
        raise HTTPException(status_code=400, detail="name and url are required")
    rss_url = (body.get("rss_url") or "").strip() or None

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

    s = Source(
        name=name, url=url, rss_url=rss_url,
        is_paywalled=bool(body.get("is_paywalled", False)),
        source_type=body.get("source_type", "other"),
        region=body.get("region", "global"), category=body.get("category"),
    )
    db.add(s)
    await db.commit()
    return {"id": s.id, "name": s.name, "updated": False}


# ── E4: hybrid search (semantic + keyword; keyword ranks above semantic-only) ──
@router.get("/search")
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
    from app.services.embeddings import embed_query_cached

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
                {"v": str(emb), "k": limit},
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
        })
    return {"query": query_str, "results": out}
