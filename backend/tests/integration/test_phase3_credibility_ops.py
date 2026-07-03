"""Phase 3 · #85 — apply a reviewed credibility score (PUT /admin/sources/{id}/credibility).

Applying a score stamps reviewed_by="admin", which locks the row against the seed re-upsert.
"""
from sqlalchemy import select

from app.models import Source, SourceType
from app.services import fetcher


async def _expert(db_session, *, score=70, meta=None):
    s = Source(
        name="Stratechery", url="https://stratechery.example", rss_url="https://stratechery.example/feed",
        source_type=SourceType.expert, region="global", category="technology",
        author_name="Ben Thompson", credibility_score=score, audience=["ai", "business"],
        credibility_meta=meta,
    )
    db_session.add(s)
    await db_session.flush()
    return s


async def test_apply_credibility_updates_and_locks(aclient, db_session):
    s = await _expert(db_session, score=70,
                      meta={"affiliation": "Stratechery LLC", "proposed_score": 85,
                            "reviewed_by": "llm-proposed"})
    r = await aclient.put(f"/admin/sources/{s.id}/credibility",
                          json={"credibility_score": 85, "rationale": "Applied the proposal."})
    assert r.status_code == 200

    fresh = (await db_session.execute(select(Source).where(Source.id == s.id))).scalar_one()
    assert fresh.credibility_score == 85
    assert fresh.credibility_meta["reviewed_by"] == "admin"          # human decision
    assert fresh.credibility_meta["affiliation"] == "Stratechery LLC"  # other keys preserved
    assert fresh.credibility_meta.get("rationale") == "Applied the proposal."


async def test_applied_score_survives_seed_reupsert(aclient, db_session):
    """After an admin applies a score, the 10-min sources.json re-upsert must not clobber it."""
    s = await _expert(db_session, score=70, meta=None)
    await aclient.put(f"/admin/sources/{s.id}/credibility", json={"credibility_score": 88})
    # sources.json ships a DIFFERENT seed score for the same feed url
    feed = {"name": "Stratechery", "url": "https://stratechery.example",
            "rss_url": "https://stratechery.example/feed", "source_type": "expert",
            "credibility_score": 82, "audience": ["ai"], "region": "global", "category": "technology"}
    await fetcher._upsert_sources(db_session, [feed])
    fresh = (await db_session.execute(select(Source).where(Source.id == s.id))).scalar_one()
    assert fresh.credibility_score == 88  # admin value held, not clobbered to 82


async def test_apply_credibility_out_of_range_is_400(aclient, db_session):
    s = await _expert(db_session)
    r = await aclient.put(f"/admin/sources/{s.id}/credibility", json={"credibility_score": 500})
    assert r.status_code == 400


async def test_apply_credibility_unknown_source_is_404(aclient, db_session):
    r = await aclient.put("/admin/sources/999999/credibility", json={"credibility_score": 80})
    assert r.status_code == 404


# ── #90 monthly LLM credibility review (propose-only) ──
from datetime import datetime, timedelta, timezone  # noqa: E402


def _stub_score(value):
    async def _score(src):
        return value
    return _score


async def test_review_proposes_for_stale_row_without_touching_live_score(db_session, monkeypatch):
    from app.services import credibility
    s = await _expert(db_session, score=70, meta=None)  # never reviewed → stale
    monkeypatch.setattr(credibility, "_propose_score", _stub_score(82))

    await credibility.review_credibility(db_session)

    fresh = (await db_session.execute(select(Source).where(Source.id == s.id))).scalar_one()
    assert fresh.credibility_meta["proposed_score"] == 82          # proposal recorded
    assert fresh.credibility_meta["reviewed_by"] == "llm-proposed"
    assert fresh.credibility_score == 70                            # LIVE score untouched


async def test_review_skips_recently_reviewed_row(db_session, monkeypatch):
    from app.services import credibility
    recent = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    s = await _expert(db_session, score=70, meta={"last_reviewed": recent})
    monkeypatch.setattr(credibility, "_propose_score", _stub_score(82))

    await credibility.review_credibility(db_session)

    fresh = (await db_session.execute(select(Source).where(Source.id == s.id))).scalar_one()
    assert "proposed_score" not in (fresh.credibility_meta or {})  # fresh → skipped


async def test_review_preserves_admin_lock(db_session, monkeypatch):
    from app.services import credibility
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    s = await _expert(db_session, score=88, meta={"reviewed_by": "admin", "last_reviewed": old})
    monkeypatch.setattr(credibility, "_propose_score", _stub_score(60))

    await credibility.review_credibility(db_session)

    fresh = (await db_session.execute(select(Source).where(Source.id == s.id))).scalar_one()
    assert fresh.credibility_meta["proposed_score"] == 60   # a fresh proposal is recorded
    assert fresh.credibility_score == 88                    # but the live score is untouched
    assert fresh.credibility_meta["reviewed_by"] == "admin"  # and the lock holds


async def test_review_no_llm_key_is_noop(db_session, monkeypatch):
    from app.services import credibility, llm
    s = await _expert(db_session, score=70, meta=None)

    async def _raise(*a, **k):
        raise llm.LLMUnavailable("no key")
    monkeypatch.setattr(llm, "generate", _raise)

    await credibility.review_credibility(db_session)  # must not crash

    fresh = (await db_session.execute(select(Source).where(Source.id == s.id))).scalar_one()
    assert "proposed_score" not in (fresh.credibility_meta or {})


async def test_review_ignores_news_tier_sources(db_session, monkeypatch):
    """The propose-only job must only touch expert/research — never burn LLM calls on the news corpus."""
    from app.services import credibility
    news = Source(name="Reuters", url="https://reuters.example", rss_url="https://reuters.example/rss",
                  source_type=SourceType.wire, region="global", category="world")  # stale (meta=None)
    expert = await _expert(db_session, score=70, meta=None)
    db_session.add(news)
    await db_session.flush()
    monkeypatch.setattr(credibility, "_propose_score", _stub_score(82))

    await credibility.review_credibility(db_session)

    fresh_news = (await db_session.execute(select(Source).where(Source.id == news.id))).scalar_one()
    fresh_expert = (await db_session.execute(select(Source).where(Source.id == expert.id))).scalar_one()
    assert "proposed_score" not in (fresh_news.credibility_meta or {})   # news untouched
    assert fresh_expert.credibility_meta["proposed_score"] == 82          # expert proposed


async def test_propose_score_survives_non_integer_llm_response(monkeypatch):
    """A JSON-parseable but non-numeric score must degrade to None, not crash the whole run."""
    from types import SimpleNamespace

    from app.services import credibility, llm

    async def _bad(*a, **k):
        return {"score": "high"}  # not an int
    monkeypatch.setattr(llm, "generate", _bad)
    src = SimpleNamespace(name="X", author_name="Y", credibility_score=70)
    assert await credibility._propose_score(src) is None


def test_is_stale_handles_garbage_and_naive_timestamps():
    from app.services import credibility
    cutoff = datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert credibility._is_stale({"last_reviewed": "not-a-date"}, cutoff) is True
    assert credibility._is_stale({"last_reviewed": "2020-01-01T00:00:00"}, cutoff) is True  # naive + old
    assert credibility._is_stale({"last_reviewed": "2099-01-01T00:00:00+00:00"}, cutoff) is False
