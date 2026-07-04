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
    """Ensure pgvector extension exists, optionally bootstrap tables, and seed default data.

    Alembic migrations are the authoritative source of schema for prod (see backend/migrations);
    the Docker start command runs `alembic upgrade head` before the server boots. `create_all` below
    is a convenience bootstrap for LOCAL DEV / TESTS ONLY and is gated behind ``init_db_create_all``
    (env ``INIT_DB_CREATE_ALL``, default true). It is OFF in prod because create_all CREATEs missing
    tables but can never ALTER an existing table to add a column — that is precisely how the prod
    schema silently drifted and 500'd every authenticated endpoint. The seeds below stay on in every
    environment (idempotent; the tables already exist via migrations in prod).
    """
    from app.database import Base
    import app.models  # noqa: F401 — ensure models are registered

    # Ensure the pgvector extension exists (idempotent; the baseline migration also creates it).
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Bootstrap tables for dev/test only. In prod (INIT_DB_CREATE_ALL=false) Alembic owns the schema.
    if settings.init_db_create_all:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("init_db_create_all_ran")
    else:
        logger.info("init_db_create_all_skipped", reason="alembic_authoritative")

    # Seed the default user via the ORM, not raw SQL: several NOT NULL users columns (locale,
    # depth_pref, persona_version, watchlist) carry only a MODEL-side default — under a create_all
    # schema they have no server_default, so a raw `INSERT (id)` NotNullViolation-s and aborts init_db
    # before topics seed. Constructing User() applies every model default uniformly (and is robust to
    # any future NOT NULL column), while created_at fills from its server_default.
    from app.models import User
    async with async_session() as session:
        existing = await session.execute(text("SELECT id FROM users LIMIT 1"))
        if existing.scalar_one_or_none() is None:
            session.add(User(id=1))  # the canonical default/single-user id (auth.DEFAULT_USER_ID)
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
    """Seed embeddings for topics that lack one. Run as background task to avoid blocking startup.

    Per-topic (WHERE embedding IS NULL), not all-or-nothing: the old "skip if ANY topic is
    embedded" early-return left topics created later (e.g. via PUT /profile interests) without
    embeddings forever, so they could only ever keyword-match.
    """
    async with async_session() as session:
        try:
            from app.services.embeddings import generate_embedding

            topic_result = await session.execute(
                text("SELECT id, name FROM topics WHERE embedding IS NULL")
            )
            topics = topic_result.all()
            if not topics:
                return  # everything already embedded
            seeded = 0
            for topic_id, topic_name in topics:
                embedding = await generate_embedding(f"News about {topic_name}")
                if embedding:
                    from app.services.embeddings import vector_literal
                    await session.execute(
                        text("UPDATE topics SET embedding = :emb WHERE id = :tid"),
                        {"emb": vector_literal(embedding), "tid": topic_id},
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
    from app.services.entities import backfill_entities
    from app.services.credibility import review_credibility
    from app.services.pubmed import ingest_pubmed
    from app.services.arxiv_gen import generate_arxiv_sources
    from app.services.lenses import backfill_tension_lines
    from app.services.graph import aggregate_entity_edges

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
    # Recurring sweep so topics created AFTER startup (e.g. via PUT /profile interests) get
    # embeddings without waiting for a restart. No-op when every topic is embedded.
    scheduler.add_job(
        seed_topic_embeddings,
        "interval",
        hours=1,
        id="topic_embedding_sweep",
        replace_existing=True,
    )
    # WS-8 (#118): one-shot RSS fetch ~5s after startup so freshness recovers AT wake — the interval
    # job otherwise fires first only at wake+rss_fetch_interval, leaving /health/fresh reporting the
    # stale pre-sleep timestamp right after a cold wake and false-alarming the keepalive + cron-job.org.
    scheduler.add_job(
        fetch_all_rss,
        "date",
        run_date=datetime.now(tz.utc) + timedelta(seconds=5),
        id="rss_fetch_kick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
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
    # G1: decoupled entity extraction on its own interval — max_instances=1 + coalesce so a slow
    # LLM batch can never overlap itself or starve the clustering loop. Dark unless enabled.
    scheduler.add_job(
        backfill_entities,
        "interval",
        minutes=settings.graph_extract_interval_minutes,
        id="entity_backfill",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    # Phase 3 · #90: monthly LLM credibility review (propose-only). 03:00 on the 1st of each month.
    # Propose-only + admin-lock-preserving, so this never mutates a live score on its own.
    scheduler.add_job(
        review_credibility,
        "cron",
        day=1,
        hour=3,
        id="credibility_review",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    # Phase 3 · #86: weekly PubMed personal research feed. 04:00 Monday. Ingests fresh abstracts for
    # each medical profession among the users; no-op when pubmed_enabled=false or no medical user.
    scheduler.add_job(
        ingest_pubmed,
        "cron",
        day_of_week="mon",
        hour=4,
        id="pubmed_ingest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    # Phase 3 · #87: weekly arXiv-by-interest source generation. 04:30 Monday. Idempotent — picks up
    # new interests (subscribed topics) and adds the matching arXiv category feeds; no-op otherwise.
    scheduler.add_job(
        generate_arxiv_sources,
        "cron",
        day_of_week="mon",
        hour=4,
        minute=30,
        id="arxiv_generate",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    # #98: discover tension-line backfill — generates a one-line story conflict per settled cluster,
    # cached on extra_json (on-change via source_hash). Dark unless tension_lines_enabled + a platform key.
    scheduler.add_job(
        backfill_tension_lines,
        "interval",
        minutes=settings.tension_interval_minutes,
        id="tension_backfill",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    # WS-5 · #115: nightly entity co-occurrence graph rebuild (02:00). Full recompute → idempotent +
    # skip-tolerant; no-op when entity_edge_enabled=false. Feeds one-hop interest expansion.
    scheduler.add_job(
        aggregate_entity_edges,
        "cron",
        hour=2,
        id="entity_edge_aggregation",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("scheduler_started", jobs=len(scheduler.get_jobs()))
    return scheduler


def init_firebase() -> bool:
    """Initialize firebase-admin EXACTLY ONCE so app/services/auth.py:verify_firebase_token works.
    No-op (warns) when no credential is configured: verify then returns None and resolve_user keeps
    serving the default user (back-compat), so local dev still runs without Firebase configured."""
    import json

    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:  # already initialized (uvicorn --reload / re-import) — second init raises
        return True
    try:
        if settings.firebase_credentials_json:
            cred = credentials.Certificate(json.loads(settings.firebase_credentials_json))
            firebase_admin.initialize_app(cred)
            logger.info("firebase_admin_initialized", source="inline_json")
        elif settings.google_application_credentials:
            cred = credentials.Certificate(settings.google_application_credentials)
            firebase_admin.initialize_app(cred)
            logger.info("firebase_admin_initialized", source="file")
        else:
            logger.warning("firebase_admin_init_skipped", reason="no_credentials")
            return False
        return True
    except Exception as e:  # noqa: BLE001 — bad/missing creds disable auth, never crash boot
        logger.warning("firebase_admin_init_failed", error=str(e))
        return False


async def check_rls_posture(db=None) -> bool:
    """Log whether the DB connection bypasses Row-Level Security. RLS enforces ONLY under a
    non-superuser role; the default `newslens` role is a SUPERUSER, so per-user isolation currently
    relies on the explicit current_user_id() filter (RLS is defense-in-depth, inert under superuser).
    Returns True when the connection is a superuser (RLS inert). Provision a restricted app role for
    production — see backend/scripts/create_app_role.sql."""
    async def _read(s):
        return (await s.execute(text("SELECT current_setting('is_superuser')"))).scalar()

    try:
        if db is not None:
            su = await _read(db)
        else:
            async with async_session() as s:
                su = await _read(s)
    except Exception as e:  # noqa: BLE001
        logger.warning("rls_posture_check_failed", error=str(e))
        return True

    is_super = su == "on"
    if is_super:
        detail = (
            "DB connection is a superuser → per-user RLS is INERT (the explicit current_user_id() "
            "filter is the only isolation control). Provision a non-superuser app role for "
            "production — backend/scripts/create_app_role.sql."
        )
        (logger.error if settings.auth_required else logger.warning)("rls_posture_warning", detail=detail)
    else:
        logger.info("rls_posture_ok")
    return is_super


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_newslens")
    try:
        await init_db()
    except Exception as e:
        logger.error("db_init_failed", error=str(e))

    try:
        init_firebase()  # one-time Admin SDK init (no-op if no credential configured)
    except Exception as e:
        logger.error("firebase_init_failed", error=str(e))

    try:
        await check_rls_posture()  # surface whether RLS is actually enforced (non-superuser role)
    except Exception as e:
        logger.warning("rls_posture_check_failed", error=str(e))

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
