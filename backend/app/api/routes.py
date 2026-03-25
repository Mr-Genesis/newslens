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
    SourceOut,
    SwipeRequest,
    TopicOut,
    TopicListResponse,
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
    except Exception:
        pass

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

    return FeedResponse(
        articles=article_outs,
        total=total,
        page=page,
        per_page=per_page,
        explore_ratio=0.3,
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
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Cluster not found")

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
    Groups top clusters by topic/category. MVP: generates from existing
    clusters without GPT (uses cluster title + first article snippet).
    """
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

    stories: list[BriefingStory] = []
    for cluster in clusters:
        # Count unique sources
        source_names = set()
        first_snippet = None
        category = "General"
        for ca in cluster.articles:
            source_names.add(ca.article.source.name)
            if first_snippet is None and ca.article.snippet:
                first_snippet = ca.article.snippet
            # Get category from first article's topic
            if category == "General" and ca.article.topics:
                for at in ca.article.topics:
                    if at.topic:
                        category = at.topic.name
                        break

        summary = cluster.summary or first_snippet or "No summary available."
        # Truncate summary to 2 sentences
        sentences = summary.split(". ")
        if len(sentences) > 2:
            summary = ". ".join(sentences[:2]) + "."

        stories.append(
            BriefingStory(
                title=cluster.title,
                summary=summary,
                cluster_id=cluster.id,
                category=category,
                source_count=len(source_names),
                coherence=0.85,  # placeholder until AI scoring
                is_read=False,
            )
        )

    # Take top 8 stories by source diversity
    stories.sort(key=lambda s: s.source_count, reverse=True)
    stories = stories[:8]

    return BriefingResponse(
        stories=stories,
        generated_at=datetime.now(timezone.utc),
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
