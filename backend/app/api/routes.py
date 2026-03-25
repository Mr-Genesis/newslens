import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session, get_db
from app.models import (
    Article,
    ClusterArticle,
    FeedbackType,
    Source,
    StoryCluster,
    Topic,
    UserFeedback,
)
from app.schemas import (
    ArticleOut,
    ClusterDetailOut,
    ClusterSourceCard,
    FeedbackCreate,
    FeedbackOut,
    FeedResponse,
    HealthResponse,
    SourceOut,
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
