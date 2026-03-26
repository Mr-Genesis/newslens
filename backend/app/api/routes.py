import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session, get_db
from app.models import (
    Article,
    ArticleTopic,
    ClusterArticle,
    FeedbackType,
    Source,
    StoryCluster,
    Topic,
    UserFeedback,
    UserPreference,
    UserSetting,
)
from app.schemas import (
    ArticleOut,
    BriefingResponse,
    BriefingStory,
    ClusterDetailOut,
    ClusterSourceCard,
    DiscoverCardOut,
    FeedbackCreate,
    FeedbackOut,
    FeedResponse,
    HealthResponse,
    KeyTestResult,
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

DEFAULT_USER_ID = 1


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


@router.get("/feed", response_model=FeedResponse)
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

    article_outs = []
    for a in articles:
        # Count how many sources cover this story (via clusters)
        cluster_count_q = (
            select(func.count(ClusterArticle.id))
            .join(ClusterArticle.cluster)
            .join(
                ClusterArticle,
                ClusterArticle.cluster_id == StoryCluster.id,
            )
            .where(ClusterArticle.article_id == a.id)
        )

        article_outs.append(
            ArticleOut(
                id=a.id,
                title=a.title,
                snippet=a.snippet,
                url=a.url,
                source=SourceOut.model_validate(a.source),
                published_at=a.published_at,
                embedding_status=a.embedding_status,
                source_count=1,
                cluster_id=None,
                has_ai_summary=False,
            )
        )

    # Compute real explore ratio from recent feedback
    from app.config import settings as app_settings
    feedback_result = await db.execute(
        select(UserFeedback.feedback_type)
        .where(UserFeedback.user_id == DEFAULT_USER_ID)
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


@router.get("/clusters/{cluster_id}", response_model=ClusterDetailOut)
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
                UserFeedback.user_id == DEFAULT_USER_ID,
                UserFeedback.article_id == article.id,
                UserFeedback.feedback_type == FeedbackType.read,
            )
        )
        if existing_read.scalar_one_or_none() is None:
            db.add(UserFeedback(
                user_id=DEFAULT_USER_ID,
                article_id=article.id,
                feedback_type=FeedbackType.read,
            ))
            await db.commit()

        return ClusterDetailOut(
            id=cluster_id,
            title=article.title,
            summary=article.snippet,
            created_at=article.published_at or article.fetched_at or datetime.now(timezone.utc),
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
                UserFeedback.user_id == DEFAULT_USER_ID,
                UserFeedback.article_id == aid,
                UserFeedback.feedback_type == FeedbackType.read,
            )
        )
        if existing_read.scalar_one_or_none() is None:
            db.add(UserFeedback(
                user_id=DEFAULT_USER_ID,
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


@router.post("/feedback", response_model=FeedbackOut, status_code=201)
async def create_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    feedback = UserFeedback(
        user_id=DEFAULT_USER_ID,
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


@router.get("/briefing", response_model=BriefingResponse)
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
            UserFeedback.user_id == DEFAULT_USER_ID,
            UserFeedback.feedback_type == FeedbackType.read,
        )
    )
    read_article_ids = set(row[0] for row in read_result.all())

    # Get user topic preference weights
    pref_result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == DEFAULT_USER_ID)
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

        stories.append(
            BriefingStory(
                title=cluster.title,
                summary=summary,
                cluster_id=cluster.id,
                category=category,
                source_count=len(source_names),
                coherence=coherence,
                is_read=is_read,
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
        .where(UserFeedback.user_id == DEFAULT_USER_ID)
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


@router.post("/discover/swipe", status_code=204)
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
        user_id=DEFAULT_USER_ID,
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
                        UserPreference.user_id == DEFAULT_USER_ID,
                        UserPreference.topic_id == at.topic_id,
                    )
                )
                pref = pref_result.scalar_one_or_none()
                if pref:
                    pref.weight = max(0.0, pref.weight + weight_delta)
                else:
                    db.add(
                        UserPreference(
                            user_id=DEFAULT_USER_ID,
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


@router.get("/settings", response_model=UserSettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Return current user settings (API key masked)."""
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == DEFAULT_USER_ID)
    )
    setting = result.scalar_one_or_none()

    if not setting or not setting.openai_api_key_encrypted:
        return UserSettingsOut(has_openai_key=False)

    from app.services.encryption import decrypt_value

    raw_key = decrypt_value(setting.openai_api_key_encrypted)
    last4 = raw_key[-4:] if len(raw_key) >= 4 else "****"

    return UserSettingsOut(
        has_openai_key=True,
        openai_key_verified=setting.openai_key_verified,
        openai_key_last4=last4,
        openai_key_verified_at=setting.openai_key_verified_at,
    )


@router.put("/settings", response_model=UserSettingsOut)
async def update_settings(
    body: UserSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Save or remove the OpenAI API key."""
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == DEFAULT_USER_ID)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        setting = UserSetting(user_id=DEFAULT_USER_ID)
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


@router.post("/settings/test-key", response_model=KeyTestResult)
async def test_api_key(db: AsyncSession = Depends(get_db)):
    """Test the saved OpenAI API key by listing models."""
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == DEFAULT_USER_ID)
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


@router.get("/saved", response_model=SavedListResponse)
async def get_saved(db: AsyncSession = Depends(get_db)):
    """Return articles saved by the user."""
    result = await db.execute(
        select(UserFeedback)
        .where(
            UserFeedback.user_id == DEFAULT_USER_ID,
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


@router.delete("/saved/{article_id}", status_code=204)
async def unsave_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove saved article by deleting the save feedback."""
    result = await db.execute(
        select(UserFeedback).where(
            UserFeedback.user_id == DEFAULT_USER_ID,
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


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Return reading stats for the user."""
    # Articles read = any feedback given
    read_result = await db.execute(
        select(func.count(func.distinct(UserFeedback.article_id))).where(
            UserFeedback.user_id == DEFAULT_USER_ID,
        )
    )
    articles_read = read_result.scalar_one() or 0

    # Stories saved
    saved_result = await db.execute(
        select(func.count()).where(
            UserFeedback.user_id == DEFAULT_USER_ID,
            UserFeedback.feedback_type == FeedbackType.save,
        )
    )
    stories_saved = saved_result.scalar_one() or 0

    # Topics explored = distinct topics from articles the user interacted with
    topics_result = await db.execute(
        select(func.count(func.distinct(ArticleTopic.topic_id)))
        .join(UserFeedback, UserFeedback.article_id == ArticleTopic.article_id)
        .where(UserFeedback.user_id == DEFAULT_USER_ID)
    )
    topics_explored = topics_result.scalar_one() or 0

    return StatsResponse(
        articles_read=articles_read,
        stories_saved=stories_saved,
        topics_explored=topics_explored,
    )
