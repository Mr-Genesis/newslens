import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import async_session, engine
from app.api.routes import router

logger = structlog.get_logger()


async def check_db() -> bool:
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False


async def init_db():
    """Create tables, ensure pgvector extension exists, and seed default user."""
    from app.database import Base
    import app.models  # noqa: F401 — ensure models are registered

    # Create pgvector extension first (before table creation needs it)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Add new columns if they don't exist (schema evolution)
    async with engine.begin() as conn:
        for stmt in [
            "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS coherence FLOAT",
            "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS summary_generated_at TIMESTAMPTZ",
            # Add 'read' to feedback_type enum if not present
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'read' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'feedbacktype')) THEN ALTER TYPE feedbacktype ADD VALUE 'read'; END IF; END $$",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                logger.debug("schema_migration_skipped", stmt=stmt[:50], error=str(e))

    # Seed default user
    async with async_session() as session:
        result = await session.execute(text("SELECT id FROM users LIMIT 1"))
        if result.scalar_one_or_none() is None:
            await session.execute(
                text("INSERT INTO users (id) VALUES (1)")
            )
        await session.commit()

    # Seed default topics
    async with async_session() as session:
        result = await session.execute(text("SELECT id FROM topics LIMIT 1"))
        if result.scalar_one_or_none() is None:
            # Insert parent topics first
            parent_topics = [
                "World", "Business", "Technology", "Politics",
                "Science", "Sports", "Health", "Entertainment",
            ]
            for name in parent_topics:
                await session.execute(
                    text("INSERT INTO topics (name) VALUES (:name)"),
                    {"name": name},
                )
            await session.flush()

            # Get parent IDs for hierarchy
            world_row = await session.execute(
                text("SELECT id FROM topics WHERE name = 'World'")
            )
            world_id = world_row.scalar_one()
            biz_row = await session.execute(
                text("SELECT id FROM topics WHERE name = 'Business'")
            )
            biz_id = biz_row.scalar_one()

            # Insert child topics with parent references
            child_topics = [
                ("India", world_id),
                ("Europe", world_id),
                ("Russia", world_id),
                ("Geo-Politics", world_id),
                ("Markets", biz_id),
                ("Start-up", biz_id),
            ]
            for name, parent_id in child_topics:
                await session.execute(
                    text(
                        "INSERT INTO topics (name, parent_topic_id) "
                        "VALUES (:name, :parent_id)"
                    ),
                    {"name": name, "parent_id": parent_id},
                )
            await session.commit()
            logger.info("topics_seeded", count=len(parent_topics) + len(child_topics))

    logger.info("database_initialized")


async def seed_topic_embeddings():
    """Seed topic embeddings if missing. Run as background task to avoid blocking startup."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM topics WHERE embedding IS NOT NULL")
        )
        if result.scalar_one() > 0:
            return  # Already seeded

        try:
            from app.services.embeddings import generate_embedding

            topic_result = await session.execute(text("SELECT id, name FROM topics"))
            topics = topic_result.all()
            seeded = 0
            for topic_id, topic_name in topics:
                embedding = await generate_embedding(f"News about {topic_name}")
                if embedding:
                    await session.execute(
                        text("UPDATE topics SET embedding = :emb WHERE id = :tid"),
                        {"emb": str(embedding), "tid": topic_id},
                    )
                    seeded += 1
            await session.commit()
            logger.info("topic_embeddings_seeded", count=seeded)
        except Exception as e:
            logger.warning("topic_embedding_seed_failed", error=str(e))


async def start_scheduler():
    """Start APScheduler for background tasks."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.services.fetcher import fetch_all_rss
    from app.services.gdelt import fetch_gdelt
    from app.services.embeddings import backfill_embeddings
    from app.services.clustering import run_clustering
    from app.services.summarizer import backfill_summaries
    from app.services.fetcher import backfill_topic_assignments

    scheduler = AsyncIOScheduler()
    # One-shot: seed topic embeddings 10s after startup (non-blocking)
    from datetime import datetime, timedelta, timezone as tz
    scheduler.add_job(
        seed_topic_embeddings,
        "date",
        run_date=datetime.now(tz.utc) + timedelta(seconds=10),
        id="topic_embedding_seed",
        replace_existing=True,
    )
    scheduler.add_job(
        fetch_all_rss,
        "interval",
        minutes=settings.rss_fetch_interval_minutes,
        id="rss_fetcher",
        replace_existing=True,
    )
    scheduler.add_job(
        fetch_gdelt,
        "interval",
        minutes=settings.gdelt_fetch_interval_minutes,
        id="gdelt_fetcher",
        replace_existing=True,
    )
    scheduler.add_job(
        backfill_embeddings,
        "interval",
        minutes=settings.embedding_backfill_interval_minutes,
        id="embedding_backfill",
        replace_existing=True,
    )
    scheduler.add_job(
        run_clustering,
        "interval",
        minutes=settings.rss_fetch_interval_minutes,
        id="clustering",
        replace_existing=True,
    )
    scheduler.add_job(
        backfill_summaries,
        "interval",
        minutes=settings.rss_fetch_interval_minutes,
        id="summary_backfill",
        replace_existing=True,
    )
    scheduler.add_job(
        backfill_topic_assignments,
        "interval",
        minutes=settings.rss_fetch_interval_minutes,
        id="topic_assignment_backfill",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler_started", jobs=len(scheduler.get_jobs()))
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_newslens")
    try:
        await init_db()
    except Exception as e:
        logger.error("db_init_failed", error=str(e))

    scheduler = None
    try:
        scheduler = await start_scheduler()
    except Exception as e:
        logger.error("scheduler_start_failed", error=str(e))

    yield

    if scheduler:
        scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("shutdown_complete")


app = FastAPI(
    title="NewsLens API",
    description="AI-powered news intelligence platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "capacitor://localhost",
        "https://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
