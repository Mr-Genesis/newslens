"""E3 (profile) + E1 (gemini key) endpoint integration tests."""
import pytest
from sqlalchemy import func, select

from app.models import (
    Article,
    ClusterArticle,
    EmbeddingStatus,
    Source,
    SourceType,
    StoryCluster,
    Topic,
    UserPreference,
)


@pytest.mark.asyncio
async def test_put_and_get_profile_with_interests(aclient, db_session):
    r = await aclient.put(
        "/profile",
        json={"profession": "cardiologist", "locale": "IN", "interests": ["Health", "Science"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["profession"] == "cardiologist"
    assert body["locale"] == "IN"
    assert set(body["interests"]) == {"Health", "Science"}

    g = await aclient.get("/profile")
    assert g.json()["profession"] == "cardiologist"
    assert set(g.json()["interests"]) == {"Health", "Science"}


@pytest.mark.asyncio
async def test_profile_accepts_arbitrary_freetext_profession(aclient, db_session):
    r = await aclient.put("/profile", json={"profession": "marine biologist"})
    assert r.status_code == 200
    assert r.json()["profession"] == "marine biologist"


@pytest.mark.asyncio
async def test_set_and_clear_gemini_key(aclient, db_session):
    r = await aclient.put("/settings/gemini-key", json={"gemini_api_key": "test-key-123"})
    assert r.status_code == 200
    assert r.json()["has_gemini_key"] is True
    r2 = await aclient.put("/settings/gemini-key", json={"gemini_api_key": None})
    assert r2.status_code == 200
    assert r2.json()["has_gemini_key"] is False


@pytest.mark.asyncio
async def test_put_profile_sets_profession_locale(aclient, db_session):
    """PUT /profile persists both profession and a non-default locale, round-tripped via GET."""
    r = await aclient.put("/profile", json={"profession": "lawyer", "locale": "US"})
    assert r.status_code == 200
    body = r.json()
    assert body["profession"] == "lawyer"
    assert body["locale"] == "US"

    g = await aclient.get("/profile")
    assert g.status_code == 200
    assert g.json()["profession"] == "lawyer"
    assert g.json()["locale"] == "US"


@pytest.mark.asyncio
async def test_interests_persist_as_preferences_not_localstorage(aclient, db_session):
    """Interests set via PUT /profile must be durable server state (user_preferences),
    not client-only localStorage. Prove it by reading the rows back from the DB and
    by getting a fresh /profile that reflects a *replacement* set."""
    r = await aclient.put(
        "/profile",
        json={"profession": "teacher", "interests": ["Economy", "Climate"]},
    )
    assert r.status_code == 200
    assert set(r.json()["interests"]) == {"Economy", "Climate"}

    # Server-side: preferences were written as real rows joined to topics by name.
    rows = (
        await db_session.execute(
            select(Topic.name)
            .join(UserPreference, UserPreference.topic_id == Topic.id)
            .where(UserPreference.user_id == 1)
        )
    ).all()
    assert {row[0] for row in rows} == {"Economy", "Climate"}

    # A new interests payload REPLACES the prior set (not append, not localStorage).
    r2 = await aclient.put("/profile", json={"interests": ["Sports"]})
    assert r2.status_code == 200
    assert set(r2.json()["interests"]) == {"Sports"}

    pref_count = (
        await db_session.execute(
            select(func.count())
            .select_from(UserPreference)
            .where(UserPreference.user_id == 1)
        )
    ).scalar()
    assert pref_count == 1

    g = await aclient.get("/profile")
    assert set(g.json()["interests"]) == {"Sports"}


@pytest.mark.asyncio
async def test_feed_personalizes_after_interests_set(aclient, db_session):
    """Setting an interest creates a topic + preference; the briefing then ranks a
    cluster tagged with that interest into the exploit slots (personalization wiring)."""
    # Set an interest — this creates the "Tech" topic and a weighted preference.
    r = await aclient.put("/profile", json={"interests": ["Tech"]})
    assert r.status_code == 200
    tech = (
        await db_session.execute(select(Topic).where(Topic.name == "Tech"))
    ).scalar_one()

    # Seed a cluster whose article is tagged with the "Tech" topic.
    src = Source(name="S", url="https://p.example/src", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    art = Article(
        title="Chip breakthrough", snippet="A long enough snippet to render as summary text.",
        url="https://p.example/a", source_id=src.id,
        embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(art)
    await db_session.flush()
    from app.models import ArticleTopic
    db_session.add(ArticleTopic(article_id=art.id, topic_id=tech.id))
    cl = StoryCluster(title="Chip story", summary="Real summary exists")
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()

    resp = await aclient.get("/briefing")
    assert resp.status_code == 200
    stories = resp.json()["stories"]
    assert any(s["cluster_id"] == cl.id and s["category"] == "Tech" for s in stories)
