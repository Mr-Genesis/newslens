"""WS-1 (#111): dwell duration on the read row + negative UER signal from 'less'. TDD."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Article,
    ClusterArticle,
    FeedbackType,
    Source,
    SourceType,
    StoryCluster,
    UserFeedback,
    UserEntityRelevance,
    Entity,
    ArticleEntity,
)
from app.services import entities as ent


async def _cluster(db, n_articles=2):
    from app.models import User
    if await db.get(User, 1) is None:
        db.add(User(id=1, locale="IN"))
        await db.flush()
    src = Source(name="dw", url="https://dw.ex", rss_url="https://dw.ex/r",
                 source_type=SourceType.wire, region="global", category="world")
    db.add(src)
    await db.flush()
    arts = []
    for i in range(n_articles):
        a = Article(title=f"d{i}", url=f"https://dw.ex/{i}", source_id=src.id,
                    published_at=datetime.now(timezone.utc))
        db.add(a)
        await db.flush()
        arts.append(a)
    c = StoryCluster(title="dw", summary="s")
    db.add(c)
    await db.flush()
    for a in arts:
        db.add(ClusterArticle(cluster_id=c.id, article_id=a.id))
    await db.flush()
    return c, arts


# ── dwell: POST /feedback read + cluster_id + duration_ms upserts the auto-read row ──
@pytest.mark.asyncio
async def test_dwell_upserts_min_article_read_row_with_greatest(aclient, db_session):
    c, arts = await _cluster(db_session)
    # opening the story creates the auto-read rows (all cluster articles)
    assert (await aclient.get(f"/clusters/{c.id}")).status_code == 200

    r = await aclient.post("/feedback", json={
        "article_id": arts[0].id,  # legacy field still required by schema; ignored for dwell target
        "feedback_type": "read", "cluster_id": c.id, "duration_ms": 30000, "surface": "briefing",
    })
    assert r.status_code == 201

    target = min(a.id for a in arts)   # deterministic dwell target = min article id in cluster
    row = (await db_session.execute(select(UserFeedback).where(
        UserFeedback.article_id == target, UserFeedback.feedback_type == FeedbackType.read
    ))).scalars().first()
    assert row is not None and row.duration_ms == 30000 and row.surface == "briefing"

    # GREATEST: a shorter re-read never shrinks recorded dwell; a longer one grows it
    await aclient.post("/feedback", json={"article_id": arts[0].id, "feedback_type": "read",
                                          "cluster_id": c.id, "duration_ms": 5000, "surface": "briefing"})
    await db_session.refresh(row)
    assert row.duration_ms == 30000
    await aclient.post("/feedback", json={"article_id": arts[0].id, "feedback_type": "read",
                                          "cluster_id": c.id, "duration_ms": 45000, "surface": "rail"})
    await db_session.refresh(row)
    assert row.duration_ms == 45000

    # no duplicate read row was created by the dwell upserts
    n = (await db_session.execute(select(UserFeedback).where(
        UserFeedback.article_id == target, UserFeedback.feedback_type == FeedbackType.read
    ))).scalars().all()
    assert len(n) == 1


# ── negative signal: 'less' demotes the article's entities in UER ──
@pytest.mark.asyncio
async def test_less_feedback_writes_negative_uer(aclient, db_session):
    c, arts = await _cluster(db_session, n_articles=1)
    e = Entity(canonical_name="Acme Corp", name_norm="acme corp", kind="org")
    db_session.add(e)
    await db_session.flush()
    db_session.add(ArticleEntity(article_id=arts[0].id, entity_id=e.id, salience=0.9, confidence=0.9))
    await db_session.flush()

    r = await aclient.post("/feedback", json={"article_id": arts[0].id, "feedback_type": "less"})
    assert r.status_code == 201

    row = (await db_session.execute(select(UserEntityRelevance).where(
        UserEntityRelevance.entity_id == e.id))).scalars().first()
    assert row is not None and row.engagement_raw < 0


@pytest.mark.asyncio
async def test_negative_bump_clamps_and_does_not_refresh_decay_clock(db_session):
    from datetime import timedelta

    from app.models import User
    if await db_session.get(User, 1) is None:
        db_session.add(User(id=1, locale="IN"))
        await db_session.flush()
    e = Entity(canonical_name="Clampy", name_norm="clampy", kind="org")
    db_session.add(e)
    await db_session.flush()

    old = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.add(UserEntityRelevance(user_id=1, entity_id=e.id, source="feedback",
                                       engagement_raw=0.4, last_event_at=old))
    await db_session.flush()

    # repeated negatives clamp at -1.0 and NEVER refresh last_event_at
    for _ in range(6):
        await ent.bump_relevance(db_session, 1, e.id, source="feedback", weight=-0.5)
    row = (await db_session.execute(select(UserEntityRelevance).where(
        UserEntityRelevance.entity_id == e.id))).scalars().first()
    assert row.engagement_raw == -1.0
    assert abs((row.last_event_at - old).total_seconds()) < 2  # decay clock untouched

    # positive bumps still refresh the clock (existing behavior preserved)
    await ent.bump_relevance(db_session, 1, e.id, source="feedback", weight=1.0)
    await db_session.flush()
    assert (datetime.now(timezone.utc) - row.last_event_at).total_seconds() < 60


@pytest.mark.asyncio
async def test_scorer_tolerates_negative_relevance(db_session):
    """A cluster whose entities the user disliked scores NEGATIVE (demotion), not an error."""
    c, arts = await _cluster(db_session, n_articles=1)
    e = Entity(canonical_name="NegCo", name_norm="negco", kind="org")
    db_session.add(e)
    await db_session.flush()
    db_session.add(ArticleEntity(article_id=arts[0].id, entity_id=e.id, salience=0.9, confidence=0.9))
    db_session.add(UserEntityRelevance(user_id=1, entity_id=e.id, source="feedback",
                                       engagement_raw=-1.0, last_event_at=datetime.now(timezone.utc)))
    await db_session.flush()
    scores = await ent.score_clusters_relevance(db_session, [c.id], 1)
    assert scores.get(c.id, 0.0) < 0.0
