"""WS-1 (#111): impression logging — the perishable rec-engine signal. TDD.

Impressions record what a user SAW (not tapped) per surface, deduped per day, capped, RLS-scoped.
Clusterless cards (briefing article-fallback) must still log + dedupe (COALESCE key — plain NULLs
never conflict in a unique index).
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import Article, ClusterArticle, Impression, Source, SourceType, StoryCluster, User


async def _cluster_with_article(db, title="s1"):
    src = Source(name=f"w-{title}", url=f"https://{title}.ex", rss_url=f"https://{title}.ex/r",
                 source_type=SourceType.wire, region="global", category="world")
    db.add(src)
    await db.flush()
    a = Article(title=title, url=f"https://{title}.ex/a", source_id=src.id,
                published_at=datetime.now(timezone.utc))
    db.add(a)
    await db.flush()
    c = StoryCluster(title=title, summary="s")
    db.add(c)
    await db.flush()
    db.add(ClusterArticle(cluster_id=c.id, article_id=a.id))
    await db.flush()
    return c, a


async def _count(db):
    return (await db.execute(select(func.count()).select_from(Impression))).scalar_one()


@pytest.mark.asyncio
async def test_batch_post_records_and_dedupes_same_day(aclient, db_session):
    c, _ = await _cluster_with_article(db_session)
    items = [{"cluster_id": c.id, "surface": "briefing"},
             {"cluster_id": c.id, "surface": "briefing"},   # dup in one batch
             {"cluster_id": c.id, "surface": "feed"}]        # same story, different surface → kept
    r = await aclient.post("/impressions", json={"items": items})
    assert r.status_code == 202
    assert await _count(db_session) == 2   # briefing once + feed once

    # A second flush the same day is a no-op for the same (story, surface).
    r2 = await aclient.post("/impressions", json={"items": [{"cluster_id": c.id, "surface": "briefing"}]})
    assert r2.status_code == 202
    assert await _count(db_session) == 2


@pytest.mark.asyncio
async def test_clusterless_article_impressions_dedupe_too(aclient, db_session):
    """Briefing fallback cards carry only article_id — NULL cluster_id must not defeat the dedupe."""
    _, a = await _cluster_with_article(db_session, "solo")
    for _ in range(3):
        r = await aclient.post("/impressions",
                               json={"items": [{"article_id": a.id, "surface": "briefing"}]})
        assert r.status_code == 202
    assert await _count(db_session) == 1


@pytest.mark.asyncio
async def test_impression_requires_a_target_and_valid_surface(aclient, db_session):
    r = await aclient.post("/impressions", json={"items": [{"surface": "briefing"}]})
    assert r.status_code == 422 or r.status_code == 400   # no cluster_id AND no article_id
    c, _ = await _cluster_with_article(db_session, "sfc")
    r2 = await aclient.post("/impressions", json={"items": [{"cluster_id": c.id, "surface": "modal"}]})
    assert r2.status_code in (400, 422)                    # unknown surface


@pytest.mark.asyncio
async def test_daily_cap_drops_beyond(aclient, db_session, monkeypatch):
    from app.config import settings as cfg
    monkeypatch.setattr(cfg, "impression_daily_cap", 3)
    clusters = [await _cluster_with_article(db_session, f"cap{i}") for i in range(5)]
    items = [{"cluster_id": c.id, "surface": "feed"} for c, _ in clusters]
    r = await aclient.post("/impressions", json={"items": items})
    assert r.status_code == 202
    assert await _count(db_session) == 3   # capped, extras dropped (logged server-side)


@pytest.mark.asyncio
async def test_impressions_are_rls_per_user(db_session):
    """Two users' impressions are isolated rows keyed by user_id (RLS-registered table)."""
    from app.models import _RLS_TABLES
    assert "impressions" in _RLS_TABLES
    c, _ = await _cluster_with_article(db_session, "rls")
    db_session.add(User(id=501))
    db_session.add(User(id=502))
    await db_session.flush()
    db_session.add(Impression(user_id=501, cluster_id=c.id, surface="feed"))
    db_session.add(Impression(user_id=502, cluster_id=c.id, surface="feed"))
    await db_session.flush()   # same story+surface+day, different users → both insert fine
    assert await _count(db_session) == 2
