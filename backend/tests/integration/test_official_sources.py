"""Official-sources Phase 1: `official` + `filing` tiers, gating, filters, hygiene.

Plan: docs/official-sources-plan.md. official = regulator/gov notices, audience-gated like
research; filing = per-company disclosures, watchlist/follow-only (audience=[]), never in discover.
"""
from datetime import datetime, timezone

import sqlalchemy as sa

from app.models import Article, Source, SourceType, User


async def test_source_supports_official_and_filing_tiers(db_session):
    db_session.add_all([
        Source(name="Federal Reserve", url="https://fed.example", rss_url="https://fed.example/rss",
               source_type=SourceType.official, region="global", category="policy",
               credibility_score=98, audience=["finance", "economics", "policy"]),
        Source(name="SEC EDGAR - NVDA", url="https://edgar.example/nvda", rss_url="https://edgar.example/nvda.atom",
               source_type=SourceType.filing, region="global", category="business",
               credibility_score=95, audience=[]),
    ])
    await db_session.flush()
    fed = (await db_session.execute(sa.select(Source).where(Source.name == "Federal Reserve"))).scalar_one()
    nvda = (await db_session.execute(sa.select(Source).where(Source.name.like("SEC EDGAR%")))).scalar_one()
    assert fed.source_type is SourceType.official
    assert nvda.source_type is SourceType.filing and nvda.audience == []


# ── gating ──
async def _set_profession(db_session, profession):
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = profession
    await db_session.flush()


async def _official(db_session, name="RBI Circulars", audience=("finance", "economics", "policy")):
    s = Source(name=name, url=f"https://{name.replace(' ', '').lower()}.example",
               rss_url=f"https://{name.replace(' ', '').lower()}.example/rss",
               source_type=SourceType.official, region="in", category="policy",
               credibility_score=97, audience=list(audience))
    db_session.add(s)
    await db_session.flush()
    db_session.add(Article(title=f"{name} item", url=f"https://{name.replace(' ', '').lower()}.example/a1",
                           source_id=s.id, snippet="A sufficiently long snippet for the feed card here.",
                           published_at=datetime(2026, 7, 4, tzinfo=timezone.utc)))
    await db_session.flush()
    return s


async def _filing(db_session, name="SEC EDGAR - NVDA"):
    s = Source(name=name, url="https://edgar.example/nvda", rss_url="https://edgar.example/nvda.atom",
               source_type=SourceType.filing, region="global", category="business",
               credibility_score=95, audience=[])
    db_session.add(s)
    await db_session.flush()
    db_session.add(Article(title="NVDA 8-K", url="https://edgar.example/nvda/8k", source_id=s.id,
                           snippet="A sufficiently long snippet for the feed card body here.",
                           published_at=datetime(2026, 7, 4, tzinfo=timezone.utc)))
    await db_session.flush()
    return s


async def _feed_titles(aclient):
    r = await aclient.get("/feed?per_page=50")
    assert r.status_code == 200
    return {a["title"] for a in r.json()["articles"]}


async def test_official_hidden_from_profession_less_user(aclient, db_session):
    await _set_profession(db_session, None)
    await _official(db_session)
    assert "RBI Circulars item" not in await _feed_titles(aclient)  # gated: poet's feed unchanged


async def test_official_visible_to_matching_profession(aclient, db_session):
    await _set_profession(db_session, "Equity trader")
    await _official(db_session)
    assert "RBI Circulars item" in await _feed_titles(aclient)  # finance tags → admitted


async def test_filing_invisible_even_to_finance_user(aclient, db_session):
    """audience=[] overlaps nothing → a filing is never audience-admitted; watchlist/follow only."""
    await _set_profession(db_session, "Equity trader")
    await _filing(db_session)
    assert "NVDA 8-K" not in await _feed_titles(aclient)


async def test_filing_visible_when_followed(aclient, db_session):
    await _set_profession(db_session, None)
    f = await _filing(db_session)
    r = await aclient.post("/follows", json={"kind": "source", "value": str(f.id)})
    assert r.status_code == 201
    assert "NVDA 8-K" in await _feed_titles(aclient)  # explicit opt-in bypasses the gate


# ── filter chip / briefing / discover ──
async def _news(db_session, name="Reuters"):
    s = Source(name=name, url=f"https://{name.lower()}.example", rss_url=f"https://{name.lower()}.example/rss",
               source_type=SourceType.wire, region="global", category="world")
    db_session.add(s)
    await db_session.flush()
    db_session.add(Article(title=f"{name} story", url=f"https://{name.lower()}.example/a1", source_id=s.id,
                           snippet="A sufficiently long snippet for the feed card here too.",
                           published_at=datetime(2026, 7, 4, tzinfo=timezone.utc)))
    await db_session.flush()
    return s


async def test_source_type_filter_accepts_official(aclient, db_session):
    await _set_profession(db_session, "Equity trader")
    await _official(db_session)
    await _news(db_session)

    r = await aclient.get("/feed?per_page=50&source_type=official")
    assert r.status_code == 200
    titles = {a["title"] for a in r.json()["articles"]}
    assert titles == {"RBI Circulars item"}

    news = {a["title"] for a in (await aclient.get("/feed?per_page=50&source_type=news")).json()["articles"]}
    assert "Reuters story" in news and "RBI Circulars item" not in news  # officials left the News bucket


async def test_briefing_exposes_official_tier_and_bonus(aclient, db_session, fake_llm):
    """A finance user's briefing includes an official cluster (gate passes) with tier='official',
    lifted into the top-8 by the field-match bonus even as the oldest cluster."""
    from datetime import timedelta

    from app.models import ClusterArticle, StoryCluster

    await _set_profession(db_session, "Equity trader")
    base = datetime(2026, 7, 4, 12, tzinfo=timezone.utc)
    rbi = await _official(db_session)
    art = (await db_session.execute(sa.select(Article).where(Article.source_id == rbi.id))).scalar_one()
    cl = StoryCluster(title="RBI Circulars item", summary="cached", coherence=0.9,
                      created_at=base - timedelta(hours=100))  # oldest of nine
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()
    for i in range(8):
        news = await _news(db_session, f"News{i}")
        a = (await db_session.execute(sa.select(Article).where(Article.source_id == news.id))).scalar_one()
        c = StoryCluster(title=f"News{i} story", summary="cached", coherence=0.9,
                         created_at=base - timedelta(hours=i))
        db_session.add(c)
        await db_session.flush()
        db_session.add(ClusterArticle(cluster_id=c.id, article_id=a.id))
        await db_session.flush()

    stories = (await aclient.get("/briefing")).json()["stories"]
    by_title = {s["title"]: s for s in stories}
    assert "RBI Circulars item" in by_title            # bonus lifted it into the top-8
    assert by_title["RBI Circulars item"]["tier"] == "official"  # badge cue


async def test_discover_deck_samples_official_but_never_filing(aclient, db_session):
    await _set_profession(db_session, None)
    await _official(db_session)      # official: allowed in the deck's opt-in sample
    await _filing(db_session)        # filing: NEVER a discover card
    for i in range(3):
        await _news(db_session, f"News{i}")

    cards = (await aclient.get("/discover/deck")).json()
    types = {c["source_type"] for c in cards}
    assert "official" in types      # opt-in surfacing works for officials
    assert "filing" not in types    # a stranger's 8-K is never a discover card
    assert all(c["is_gated"] for c in cards if c["source_type"] == "official")


# ── admin validation + credibility-review exclusion ──
async def test_admin_create_official_requires_credibility(aclient):
    r = await aclient.post("/admin/sources", json={
        "name": "Some Ministry", "url": "https://ministry.example", "source_type": "official",
    })
    assert r.status_code == 400  # gated tiers are admission-controlled — no score, no publish


async def test_review_job_never_scores_officials(db_session, monkeypatch):
    """Scoring the Federal Reserve is meaningless — the monthly LLM review skips official/filing."""
    from app.services import credibility

    fed = Source(name="Federal Reserve", url="https://fed.example", rss_url="https://fed.example/rss",
                 source_type=SourceType.official, region="global", category="policy",
                 credibility_score=98, audience=["finance"], credibility_meta=None)  # stale
    db_session.add(fed)
    await db_session.flush()

    async def _score(src):
        return 55
    monkeypatch.setattr(credibility, "_propose_score", _score)
    await credibility.review_credibility(db_session)

    fresh = (await db_session.execute(sa.select(Source).where(Source.id == fed.id))).scalar_one()
    assert "proposed_score" not in (fresh.credibility_meta or {})  # official → skipped
