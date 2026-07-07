"""WS-2 (#112): GET /follows/rails + badges + cap + isolation. Topic/entity rails are tested
end-to-end (no embeddings needed); saved_search's semantic leg is covered by test_rails_admit +
the graceful-degrade test here."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Article,
    ArticleEntity,
    ArticleTopic,
    ClusterArticle,
    Entity,
    Follow,
    Source,
    SourceType,
    StoryCluster,
    Topic,
    User,
)
from app.services import rails as rails_svc


async def _ensure_user(db, uid=1):
    if await db.get(User, uid) is None:
        db.add(User(id=uid, locale="IN"))
        await db.flush()


async def _story(db, title, *, topic=None, entity=None, hours_ago=1):
    src = Source(name=f"s-{title}", url=f"https://{title}.ex", rss_url=f"https://{title}.ex/r",
                 source_type=SourceType.wire, region="global", category="world")
    db.add(src)
    await db.flush()
    art = Article(title=title, url=f"https://{title}.ex/a", source_id=src.id,
                  published_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago))
    db.add(art)
    await db.flush()
    c = StoryCluster(title=title, summary=f"summary of {title}")
    db.add(c)
    await db.flush()
    db.add(ClusterArticle(cluster_id=c.id, article_id=art.id))
    if topic is not None:
        t = (await db.execute(select(Topic).where(Topic.name == topic))).scalars().first()
        if t is None:
            t = Topic(name=topic)
            db.add(t)
            await db.flush()
        db.add(ArticleTopic(article_id=art.id, topic_id=t.id))
    if entity is not None:
        db.add(ArticleEntity(article_id=art.id, entity_id=entity.id, salience=0.9, confidence=0.9))
    await db.flush()
    return c, art


@pytest.fixture(autouse=True)
def _clear_rail_cache():
    rails_svc._cache.clear()
    rails_svc._generation.clear()
    yield
    rails_svc._cache.clear()
    rails_svc._generation.clear()


@pytest.mark.asyncio
async def test_topic_follow_gets_a_rail_with_its_stories(aclient, db_session):
    await _ensure_user(db_session)
    c, _ = await _story(db_session, "Mars landing", topic="Space")
    await _story(db_session, "Unrelated", topic="Cooking")
    db_session.add(Follow(user_id=1, kind="topic", value="Space"))
    await db_session.flush()

    r = await aclient.get("/follows/rails")
    assert r.status_code == 200
    rails = r.json()["rails"]
    space = next(x for x in rails if x["value"] == "Space")
    assert space["total"] == 1
    assert {s["cluster_id"] for s in space["stories"]} == {c.id}
    assert space["new_count"] == 1  # never viewed → all new


@pytest.mark.asyncio
async def test_entity_follow_gets_a_rail(aclient, db_session):
    await _ensure_user(db_session)
    e = Entity(canonical_name="NASA", name_norm="nasa", kind="org")
    db_session.add(e)
    await db_session.flush()
    c, _ = await _story(db_session, "NASA budget", entity=e)
    db_session.add(Follow(user_id=1, kind="entity", value="NASA", entity_id=e.id))
    await db_session.flush()

    rails = (await aclient.get("/follows/rails")).json()["rails"]
    nasa = next(x for x in rails if x["value"] == "NASA")
    assert {s["cluster_id"] for s in nasa["stories"]} == {c.id}


@pytest.mark.asyncio
async def test_source_follows_are_not_rails(aclient, db_session):
    await _ensure_user(db_session)
    src = (await db_session.execute(select(Source))).scalars().first()
    if src is None:
        src = Source(name="src", url="https://src.ex", rss_url="https://src.ex/r",
                     source_type=SourceType.wire, region="global", category="world")
        db_session.add(src)
        await db_session.flush()
    db_session.add(Follow(user_id=1, kind="source", value=str(src.id)))
    await db_session.flush()
    rails = (await aclient.get("/follows/rails")).json()["rails"]
    assert all(x["kind"] != "source" for x in rails)


@pytest.mark.asyncio
async def test_recency_window_excludes_old_stories(aclient, db_session):
    await _ensure_user(db_session)
    await _story(db_session, "Fresh", topic="News", hours_ago=1)
    await _story(db_session, "Ancient", topic="News", hours_ago=200)  # > 72h window
    db_session.add(Follow(user_id=1, kind="topic", value="News"))
    await db_session.flush()
    rails = (await aclient.get("/follows/rails")).json()["rails"]
    news = next(x for x in rails if x["value"] == "News")
    assert news["total"] == 1  # only the fresh one


@pytest.mark.asyncio
async def test_seen_clears_badge_but_digest_does_not(aclient, db_session):
    """The core badge contract: /seen zeroes new_count for THAT follow; reading /digest must NOT."""
    await _ensure_user(db_session)
    await _story(db_session, "Quake", topic="Geo")
    f = Follow(user_id=1, kind="topic", value="Geo")
    db_session.add(f)
    await db_session.flush()

    rails_svc._cache.clear()
    before = next(x for x in (await aclient.get("/follows/rails")).json()["rails"] if x["value"] == "Geo")
    assert before["new_count"] == 1

    # reading the digest must not clear the rail badge (regression vs the global last_seen_at)
    await aclient.get("/digest")
    rails_svc._cache.clear()
    still = next(x for x in (await aclient.get("/follows/rails")).json()["rails"] if x["value"] == "Geo")
    assert still["new_count"] == 1

    # tapping the rail (POST /seen) clears it
    assert (await aclient.post(f"/follows/{f.id}/seen")).status_code == 204
    rails_svc._cache.clear()
    after = next(x for x in (await aclient.get("/follows/rails")).json()["rails"] if x["value"] == "Geo")
    assert after["new_count"] == 0


@pytest.mark.asyncio
async def test_saved_search_cap(aclient, db_session):
    await _ensure_user(db_session)
    from app.config import settings
    for i in range(settings.saved_search_cap):
        r = await aclient.post("/follows", json={"kind": "saved_search", "value": f"topic {i}"})
        assert r.status_code == 201
    over = await aclient.post("/follows", json={"kind": "saved_search", "value": "one too many"})
    assert over.status_code == 400


@pytest.mark.asyncio
async def test_one_failing_rail_does_not_kill_the_section(aclient, db_session, monkeypatch):
    await _ensure_user(db_session)
    await _story(db_session, "Good", topic="Good")
    db_session.add(Follow(user_id=1, kind="topic", value="Good"))
    db_session.add(Follow(user_id=1, kind="saved_search", value="boom"))
    await db_session.flush()

    async def _boom(db, phrase, since):
        raise RuntimeError("semantic leg exploded")

    monkeypatch.setattr(rails_svc, "evaluate_saved_search", _boom)
    rails_svc._cache.clear()
    rails = (await aclient.get("/follows/rails")).json()["rails"]
    values = {x["value"] for x in rails}
    assert "Good" in values          # the healthy rail survived
    assert "boom" not in values      # the exploded rail was dropped, not fatal


@pytest.mark.asyncio
async def test_invalidate_mid_build_skips_stale_cache_write(db_session, monkeypatch):
    """LOW (review): a create/delete/seen that lands WHILE rails_for_user is building must not be
    masked by a stale write-back for a full TTL. Simulate the race by invalidating during the build."""
    await _ensure_user(db_session)
    await _story(db_session, "Flood", topic="Weather")
    db_session.add(Follow(user_id=1, kind="topic", value="Weather"))
    await db_session.flush()
    rails_svc._cache.clear()
    rails_svc._generation.clear()

    real_eval = rails_svc.evaluate_topic

    async def _eval_then_invalidate(db, name, since):
        out = await real_eval(db, name, since)
        rails_svc.invalidate(1)  # a concurrent mutation lands mid-build
        return out

    monkeypatch.setattr(rails_svc, "evaluate_topic", _eval_then_invalidate)
    await rails_svc.rails_for_user(db_session, 1)
    # The generation advanced during the build → the stale result was NOT cached.
    assert 1 not in rails_svc._cache


@pytest.mark.asyncio
async def test_topic_and_saved_search_same_value_dedupe_to_one_rail(aclient, db_session):
    """Adversarial-review fix: a `topic` follow and a `saved_search` follow may legally share a value
    (uq_follow keys on kind too), which the interests↔topic-follow unify makes likely. Rails must
    collapse them to a SINGLE 'AI' header, keeping the precise topic rail — not render two identical
    headers over overlapping clusters."""
    await _ensure_user(db_session)
    c, _ = await _story(db_session, "AI breakthrough", topic="AI")
    db_session.add(Follow(user_id=1, kind="topic", value="AI"))
    db_session.add(Follow(user_id=1, kind="saved_search", value="AI"))
    await db_session.flush()

    rails = (await aclient.get("/follows/rails")).json()["rails"]
    ai_rails = [x for x in rails if x["value"].strip().lower() == "ai"]
    assert len(ai_rails) == 1                                   # collapsed, not two identical headers
    assert ai_rails[0]["kind"] == "topic"                       # kept the precise ArticleTopic match
    assert {s["cluster_id"] for s in ai_rails[0]["stories"]} == {c.id}
