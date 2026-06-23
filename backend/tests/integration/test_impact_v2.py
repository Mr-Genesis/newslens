"""Wave A: impact engine v2 end-to-end — contract, persona cache, TTL, refresh,
retry-exhaustion, and adversarial guardrail neutralization. Runs in Docker (real PG)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    Article, ClusterArticle, EmbeddingStatus, Source, SourceType,
    StoryCluster, Topic, User, UserPreference,
)
from app.services import lenses

_n = 0


async def _seed(db, outlet="S"):
    global _n
    _n += 1
    src = Source(name=outlet, url=f"https://x/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    a = Article(title="T", snippet="detail", url=f"https://x/{_n}/a",
                source_id=src.id, embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    cl = StoryCluster(title="C", summary="Summary sentence one. Sentence two.")
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return cl


async def _set_profession(db, profession, interests=None):
    u = await db.get(User, 1)
    if u is None:
        u = User(id=1, profession=profession, locale="IN")
        db.add(u)
    else:
        u.profession = profession
    await db.flush()
    for name in interests or []:
        t = Topic(name=name)
        db.add(t)
        await db.flush()
        db.add(UserPreference(user_id=1, topic_id=t.id, weight=1.0))
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_impact_returns_structured_contract(aclient, db_session, fake_llm):
    await _set_profession(db_session, "Engineer")
    cl = await _seed(db_session)
    r = await aclient.get(f"/clusters/{cl.id}/impact")
    assert r.status_code == 200
    b = r.json()
    assert b["cached"] is False
    assert 0 <= b["personal_relevance"]["score"] <= 100
    assert b["personal_relevance"]["one_liner"]
    assert set(b["dimensions"]) == {"professional", "financial", "civic"}
    assert b["dimensions"]["financial"]["not_advice"] is True
    assert b["dimensions"]["professional"]["horizon"] in ("now", "weeks", "quarter", "year_plus")
    assert fake_llm["generate"] == 1


@pytest.mark.asyncio
async def test_impact_distinct_per_persona(aclient, db_session, fake_llm):
    cl = await _seed(db_session)
    await _set_profession(db_session, "Nurse")
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is False
    assert fake_llm["generate"] == 1
    await _set_profession(db_session, "Trader")  # different persona → different hash → miss
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is False
    assert fake_llm["generate"] == 2


@pytest.mark.asyncio
async def test_persona_version_bump_invalidates(aclient, db_session, fake_llm):
    await _set_profession(db_session, "Engineer")
    cl = await _seed(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is False
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is True
    assert fake_llm["generate"] == 1
    # an (empty) profile edit bumps persona_version → next impact is a cache miss
    await aclient.put("/profile", json={})
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is False
    assert fake_llm["generate"] == 2


@pytest.mark.asyncio
async def test_impact_refresh_bypasses_cache(aclient, db_session, fake_llm):
    await _set_profession(db_session, "Engineer")
    cl = await _seed(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is False
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is True
    assert fake_llm["generate"] == 1
    assert (await aclient.get(f"/clusters/{cl.id}/impact?refresh=1")).json()["cached"] is False
    assert fake_llm["generate"] == 2


@pytest.mark.asyncio
async def test_impact_ttl_expiry(aclient, db_session, fake_llm, monkeypatch):
    await _set_profession(db_session, "Engineer")
    cl = await _seed(db_session)
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is False
    assert fake_llm["generate"] == 1
    monkeypatch.setattr(
        lenses, "_utcnow", lambda: datetime.now(timezone.utc) + timedelta(hours=25)
    )
    assert (await aclient.get(f"/clusters/{cl.id}/impact")).json()["cached"] is False
    assert fake_llm["generate"] == 2


@pytest.mark.asyncio
async def test_impact_profession_unset_short_circuits(aclient, db_session, fake_llm):
    await _set_profession(db_session, None)
    cl = await _seed(db_session)
    b = (await aclient.get(f"/clusters/{cl.id}/impact")).json()
    assert b.get("unavailable") is True and b.get("reason") == "profession_unset"
    assert fake_llm["generate"] == 0


# ── retry-exhaustion paths ──
@pytest.fixture
def fake_llm_invalid(monkeypatch):
    calls = {"generate": 0}

    async def _gen(prompt, *, system=None, schema=None, model=None, max_tokens=None):
        calls["generate"] += 1
        return {"not": "a valid impact"}  # fails StoryImpact validation every time

    import app.services.llm as llm
    monkeypatch.setattr(llm, "generate", _gen)
    return calls


@pytest.mark.asyncio
async def test_impact_invalid_twice_returns_unavailable(aclient, db_session, fake_llm_invalid):
    await _set_profession(db_session, "Engineer")
    cl = await _seed(db_session)
    b = (await aclient.get(f"/clusters/{cl.id}/impact")).json()
    assert b.get("unavailable") is True and b.get("reason") == "impact_invalid"
    assert fake_llm_invalid["generate"] == 2  # one bounded retry


@pytest.fixture
def fake_llm_adversarial(monkeypatch):
    calls = {"generate": 0}

    async def _gen(prompt, *, system=None, schema=None, model=None, max_tokens=None):
        calls["generate"] += 1
        return {
            "headline": "A massive game-changer.",  # hype
            "personal_relevance": {"score": 80, "one_liner": "Big for you."},
            "dimensions": {
                "professional": {
                    "applicable": True, "relevance": "Matters to your role.",
                    "mechanism": "", "watch_items": [], "horizon": "weeks",
                    "confidence": "medium", "confidence_rationale": "",
                    "evidence": [{"claim": "x", "source": "Reuters"}],  # not in outlets
                },
                "financial": {
                    "applicable": True, "relevance": "You should buy the dip.",  # advice
                    "mechanism": "Shares will rise.", "watch_items": ["sell calls"],
                    "horizon": "now", "confidence": "high", "confidence_rationale": "",
                    "evidence": [],
                },
                "civic": {
                    "applicable": False, "relevance": "", "mechanism": "",
                    "watch_items": [], "horizon": "year_plus", "confidence": "low",
                    "confidence_rationale": "", "evidence": [],
                },
            },
            "caveats": "",
        }

    import app.services.llm as llm
    monkeypatch.setattr(llm, "generate", _gen)
    return calls


@pytest.mark.asyncio
async def test_impact_adversarial_is_neutralized(aclient, db_session, fake_llm_adversarial):
    await _set_profession(db_session, "Engineer")
    cl = await _seed(db_session, outlet="S")
    b = (await aclient.get(f"/clusters/{cl.id}/impact")).json()
    assert b["dimensions"]["financial"]["applicable"] is False  # advice survived → dropped
    assert b["dimensions"]["financial"]["not_advice"] is True
    assert b["dimensions"]["professional"]["evidence"] == []     # ungrounded source dropped
    assert fake_llm_adversarial["generate"] == 2                 # regenerated once on advice+hype
