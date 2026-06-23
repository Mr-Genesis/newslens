"""E5/E6/E7/E8: cluster lens endpoints — generate + cache + graceful unavailable."""
import itertools

import pytest

from app.models import (
    Article,
    ArticleTopic,
    ClusterArticle,
    EmbeddingStatus,
    Source,
    SourceType,
    StoryCluster,
    Topic,
    User,
)
from app.services import lenses

_src_seq = itertools.count(1)


async def _seed_cluster(db_session, n=2):
    # Unique source url per call so tests that seed multiple clusters don't collide
    # on the sources.url unique constraint.
    src = Source(name="S", url=f"https://l.example/src/{next(_src_seq)}", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    arts = []
    for i in range(n):
        a = Article(
            title=f"Story {i}", snippet="detail text", url=f"https://l.example/{i}",
            source_id=src.id, embedding_status=EmbeddingStatus.complete,
        )
        db_session.add(a)
        arts.append(a)
    cl = StoryCluster(title="Cluster", summary="s")
    db_session.add(cl)
    await db_session.flush()
    for a in arts:
        db_session.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db_session.flush()
    cl._articles = arts  # convenience handle for tests that mutate the source set
    return cl


async def _set_profession(db_session, profession):
    """Ensure the default user (id=1, read by the routes) has the given profession."""
    u = await db_session.get(User, 1)
    if u is None:
        u = User(id=1, profession=profession, locale="IN")
        db_session.add(u)
    else:
        u.profession = profession
    await db_session.flush()
    return u


async def _tag_cluster_topic(db_session, cluster, topic_name):
    """Attach a Topic (by name) to every article in the cluster (strategic topic-gate)."""
    topic = Topic(name=topic_name)
    db_session.add(topic)
    await db_session.flush()
    for a in cluster._articles:
        db_session.add(
            ArticleTopic(article_id=a.id, topic_id=topic.id, relevance_score=1.0)
        )
    await db_session.flush()
    return topic


# ── E5: analysis lenses (key_facts / 5ws / profession) ──
@pytest.mark.asyncio
async def test_analysis_keyfacts_returns_bullets_and_caches(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    r1 = await aclient.get(f"/clusters/{cl.id}/analysis?lens=key_facts")
    assert r1.status_code == 200
    body = r1.json()
    assert body.get("cached") is False
    assert isinstance(body["facts"], list) and len(body["facts"]) >= 1
    assert fake_llm["generate"] == 1
    # second call serves from cache — no new LLM call
    r2 = await aclient.get(f"/clusters/{cl.id}/analysis?lens=key_facts")
    assert r2.json().get("cached") is True
    assert r2.json()["facts"] == body["facts"]
    assert fake_llm["generate"] == 1


@pytest.mark.asyncio
async def test_analysis_5ws_returns_five_keys(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    r = await aclient.get(f"/clusters/{cl.id}/analysis?lens=5ws")
    assert r.status_code == 200
    body = r.json()
    for key in ("who", "what", "when", "where", "why"):
        assert key in body and isinstance(body[key], str) and body[key]


@pytest.mark.asyncio
async def test_analysis_profession_lens_uses_profile(aclient, db_session, fake_llm):
    await _set_profession(db_session, "nurse")
    cl = await _seed_cluster(db_session)
    r = await aclient.get(f"/clusters/{cl.id}/analysis?lens=profession")
    assert r.status_code == 200
    body = r.json()
    assert body.get("cached") is False
    assert "headline" in body
    assert isinstance(body["points"], list) and len(body["points"]) >= 1
    # cache subkey is keyed by the profession hash, so a re-request hits cache
    r2 = await aclient.get(f"/clusters/{cl.id}/analysis?lens=profession")
    assert r2.json().get("cached") is True
    assert fake_llm["generate"] == 1


# ── E6: WIIFM impact (profession-hash cache + source-hash invalidation) ──
@pytest.mark.asyncio
async def test_impact_reuses_cache_per_profession_hash(aclient, db_session, fake_llm):
    await _set_profession(db_session, "Software Engineer")
    cl = await _seed_cluster(db_session)
    r1 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r1.status_code == 200
    assert r1.json().get("cached") is False
    assert fake_llm["generate"] == 1
    r2 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r2.json().get("cached") is True
    assert fake_llm["generate"] == 1
    # same profession in a different casing/whitespace hashes identically -> still cached
    await _set_profession(db_session, "  software engineer ")
    r3 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r3.json().get("cached") is True
    assert fake_llm["generate"] == 1


@pytest.mark.asyncio
async def test_impact_invalidates_on_source_hash_change(aclient, db_session, fake_llm):
    await _set_profession(db_session, "teacher")
    cl = await _seed_cluster(db_session)
    r1 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r1.json().get("cached") is False
    assert fake_llm["generate"] == 1
    # add a new source article -> the source_hash changes -> cache is stale
    new_art = Article(
        title="Story NEW", snippet="more detail", url="https://l.example/new",
        source_id=cl._articles[0].source_id, embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(new_art)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=new_art.id))
    await db_session.flush()
    r2 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r2.json().get("cached") is False  # regenerated against the new source set
    assert fake_llm["generate"] == 2


@pytest.mark.asyncio
async def test_impact_unavailable_when_profession_unset(aclient, db_session, fake_llm):
    # No profession on the default user -> impact has no meaningful answer.
    await _set_profession(db_session, None)
    cl = await _seed_cluster(db_session)
    r = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r.status_code == 200
    body = r.json()
    assert body.get("unavailable") is True
    assert body.get("reason") == "profession_unset"
    assert fake_llm["generate"] == 0  # short-circuits before any LLM call


@pytest.mark.asyncio
async def test_profession_hash_stable_and_normalized():
    # Same logical profession (case/whitespace-insensitive) -> same hash.
    assert lenses.profession_hash("Doctor") == lenses.profession_hash("  doctor ")
    assert lenses.profession_hash("doctor") != lenses.profession_hash("lawyer")
    # Empty / None normalize to a stable sentinel.
    assert lenses.profession_hash(None) == "default"
    assert lenses.profession_hash("   ") == "default"


# ── E7: strategic / game-theory (topic-gated) ──
@pytest.mark.asyncio
async def test_strategic_returns_structured_actors_and_game_type(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    await _tag_cluster_topic(db_session, cl, "Geopolitics")
    r = await aclient.get(f"/clusters/{cl.id}/strategic")
    assert r.status_code == 200
    body = r.json()
    assert body.get("cached") is False
    assert isinstance(body["actors"], list) and len(body["actors"]) >= 1
    for actor in body["actors"]:
        assert {"name", "incentive", "likely_move"} <= set(actor)
    assert isinstance(body["game_type"], str) and body["game_type"]


@pytest.mark.asyncio
async def test_strategic_caches(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    await _tag_cluster_topic(db_session, cl, "World")
    r1 = await aclient.get(f"/clusters/{cl.id}/strategic")
    assert r1.json().get("cached") is False
    assert fake_llm["generate"] == 1
    r2 = await aclient.get(f"/clusters/{cl.id}/strategic")
    assert r2.json().get("cached") is True
    assert fake_llm["generate"] == 1


@pytest.mark.asyncio
async def test_strategic_schema_validates_required_fields(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    await _tag_cluster_topic(db_session, cl, "International Politics")
    body = (await aclient.get(f"/clusters/{cl.id}/strategic")).json()
    assert {"actors", "game_type", "second_order", "non_obvious_take"} <= set(body)
    assert isinstance(body["second_order"], list)
    assert isinstance(body["non_obvious_take"], str)


@pytest.mark.asyncio
async def test_strategic_offered_only_for_geopolitics_topics(aclient, db_session, fake_llm):
    # Non-geopolitics topic -> the lens is not offered.
    cl_other = await _seed_cluster(db_session)
    await _tag_cluster_topic(db_session, cl_other, "Cooking")
    r_other = await aclient.get(f"/clusters/{cl_other.id}/strategic")
    assert r_other.status_code == 200
    body = r_other.json()
    assert body.get("unavailable") is True
    assert body.get("reason") == "not_offered_for_topic"
    assert fake_llm["generate"] == 0

    # Geopolitics topic -> offered + generated.
    cl_geo = await _seed_cluster(db_session)
    await _tag_cluster_topic(db_session, cl_geo, "Geopolitics")
    r_geo = await aclient.get(f"/clusters/{cl_geo.id}/strategic")
    assert r_geo.status_code == 200
    assert "unavailable" not in r_geo.json()
    assert fake_llm["generate"] == 1


# ── E8: trivia (easy / medium / hard) ──
@pytest.mark.asyncio
async def test_trivia_returns_questions_for_each_difficulty(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    for i, diff in enumerate(("easy", "medium", "hard"), start=1):
        r = await aclient.get(f"/clusters/{cl.id}/trivia?difficulty={diff}")
        assert r.status_code == 200
        questions = r.json()["questions"]
        assert isinstance(questions, list) and len(questions) >= 1
        assert fake_llm["generate"] == i  # each difficulty is a distinct subkey


@pytest.mark.asyncio
async def test_trivia_each_question_has_answer_and_explanation(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    body = (await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=medium")).json()
    for q in body["questions"]:
        assert isinstance(q["question"], str) and q["question"]
        assert isinstance(q["options"], list) and len(q["options"]) == 4
        assert isinstance(q["answer_index"], int)
        assert 0 <= q["answer_index"] < len(q["options"])
        assert isinstance(q["explanation"], str) and q["explanation"]


@pytest.mark.asyncio
async def test_trivia_invalid_difficulty_400(aclient, db_session):
    cl = await _seed_cluster(db_session)
    r = await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=bogus")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_trivia_caches_per_difficulty(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    r1 = await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=hard")
    assert r1.json().get("cached") is False
    assert fake_llm["generate"] == 1
    # same difficulty -> cache hit
    r2 = await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=hard")
    assert r2.json().get("cached") is True
    assert fake_llm["generate"] == 1
    # different difficulty -> distinct subkey -> regenerates
    r3 = await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=easy")
    assert r3.json().get("cached") is False
    assert fake_llm["generate"] == 2


@pytest.mark.asyncio
async def test_impact_generates_then_serves_from_cache(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    await _set_profession(db_session, "Analyst")  # impact requires a profession to generate
    r1 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r1.status_code == 200
    assert r1.json().get("cached") is False
    assert fake_llm["generate"] == 1
    r2 = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r2.json().get("cached") is True
    assert fake_llm["generate"] == 1  # cache hit, no second LLM call


@pytest.mark.asyncio
async def test_analysis_keyfacts_and_5ws_generate(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/analysis?lens=key_facts")).status_code == 200
    assert (await aclient.get(f"/clusters/{cl.id}/analysis?lens=5ws")).status_code == 200
    assert fake_llm["generate"] == 2  # two distinct sub-lenses


@pytest.mark.asyncio
async def test_analysis_invalid_lens_400(aclient, db_session):
    cl = await _seed_cluster(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/analysis?lens=bogus")).status_code == 400


@pytest.mark.asyncio
async def test_strategic_and_trivia(aclient, db_session, fake_llm):
    cl = await _seed_cluster(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/strategic")).status_code == 200
    assert (await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=hard")).status_code == 200
    assert (await aclient.get(f"/clusters/{cl.id}/trivia?difficulty=bogus")).status_code == 400


@pytest.mark.asyncio
async def test_impact_graceful_when_llm_fails(aclient, db_session):
    # No fake_llm -> real seam. Whether the key is missing or the API errors
    # (e.g. quota), the lens must return a typed unavailable, never a 500.
    cl = await _seed_cluster(db_session)
    r = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r.status_code == 200
    assert r.json().get("unavailable") is True
