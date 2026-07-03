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


# ── review fixes: the ungated surfaces (digest, topic cards) + admin audience contract ──
async def _cluster_for(db_session, source, title):
    from app.models import ClusterArticle, StoryCluster
    art = (await db_session.execute(
        sa.select(Article).where(Article.source_id == source.id))).scalars().first()
    cl = StoryCluster(title=title, summary="cached", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()
    return cl


async def test_digest_gates_official_clusters(aclient, db_session):
    """/digest (the WhileAwayCard) must apply the same persona gate as the briefing — officials form
    singleton clusters and would otherwise leak onto every user's home screen."""
    await _set_profession(db_session, None)
    rbi = await _official(db_session)
    news = await _news(db_session)
    await _cluster_for(db_session, rbi, "RBI Circulars item")
    await _cluster_for(db_session, news, "Reuters story")

    items = (await aclient.get("/digest")).json()["items"]
    titles = {i["title"] for i in items}
    assert "Reuters story" in titles
    assert "RBI Circulars item" not in titles  # gated out for a profession-less user


async def test_topic_cards_never_serve_gated_sources(aclient, db_session):
    """/discover/topic/{id} (swipe-up cards) must exclude ALL gated tiers — gated content only ever
    arrives via the deck's flagged opt-in sample, never as unflagged topic cards."""
    from app.models import ArticleTopic, Topic

    await _set_profession(db_session, None)
    rbi = await _official(db_session)
    filing = await _filing(db_session)
    news = await _news(db_session)
    topic = Topic(name="Policy")
    db_session.add(topic)
    await db_session.flush()
    for src in (rbi, filing, news):
        art = (await db_session.execute(
            sa.select(Article).where(Article.source_id == src.id))).scalars().first()
        db_session.add(ArticleTopic(article_id=art.id, topic_id=topic.id))
    await db_session.flush()

    cards = (await aclient.get(f"/discover/topic/{topic.id}")).json()
    titles = {c["title"] for c in cards}
    assert "Reuters story" in titles
    assert "RBI Circulars item" not in titles and "NVDA 8-K" not in titles


async def test_admin_official_requires_audience_and_filing_forces_empty(aclient, db_session):
    """The audience contract is enforced at the write boundary: an official without audience would be
    NULL = visible to EVERYONE (defeats the tier) → 400; a filing is always forced to audience=[]
    (watchlist/follow-only) no matter what the caller sends."""
    r = await aclient.post("/admin/sources", json={
        "name": "Some Regulator", "url": "https://reg.example", "source_type": "official",
        "credibility_score": 95,  # no audience → 400
    })
    assert r.status_code == 400

    r2 = await aclient.post("/admin/sources", json={
        "name": "EDGAR NVDA", "url": "https://edgar2.example", "rss_url": "https://edgar2.example/atom",
        "source_type": "filing", "credibility_score": 95, "audience": ["finance"],  # ignored
    })
    assert r2.status_code == 200
    row = (await db_session.execute(
        sa.select(Source).where(Source.url == "https://edgar2.example"))).scalar_one()
    assert row.audience == []  # forced watchlist-only, caller's audience ignored


async def test_briefing_hides_official_from_profession_less_user(aclient, db_session, fake_llm):
    await _set_profession(db_session, None)
    rbi = await _official(db_session)
    news = await _news(db_session)
    await _cluster_for(db_session, rbi, "RBI Circulars item")
    await _cluster_for(db_session, news, "Reuters story")

    titles = {s["title"] for s in (await aclient.get("/briefing")).json()["stories"]}
    assert "Reuters story" in titles and "RBI Circulars item" not in titles


async def test_filter_filing_roundtrip_with_follow(aclient, db_session):
    """?source_type=filing: empty for a non-follower; the follower sees exactly their filings."""
    await _set_profession(db_session, None)
    f = await _filing(db_session)
    empty = (await aclient.get("/feed?per_page=50&source_type=filing")).json()["articles"]
    assert empty == []

    await aclient.post("/follows", json={"kind": "source", "value": str(f.id)})
    titles = {a["title"] for a in
              (await aclient.get("/feed?per_page=50&source_type=filing")).json()["articles"]}
    assert titles == {"NVDA 8-K"}


async def test_below_floor_official_hidden_unless_followed(aclient, db_session):
    """Floors apply to officials too — and the follow-override still wins."""
    await _set_profession(db_session, "Equity trader")
    low = Source(name="Minor Agency", url="https://minor.example", rss_url="https://minor.example/rss",
                 source_type=SourceType.official, region="global", category="policy",
                 credibility_score=40, audience=["finance"])  # 40 < feed floor 55
    db_session.add(low)
    await db_session.flush()
    db_session.add(Article(title="Minor notice", url="https://minor.example/a1", source_id=low.id,
                           snippet="A sufficiently long snippet for the feed card body here.",
                           published_at=datetime(2026, 7, 4, tzinfo=timezone.utc)))
    await db_session.flush()

    assert "Minor notice" not in await _feed_titles(aclient)          # below floor → hidden
    await aclient.post("/follows", json={"kind": "source", "value": str(low.id)})
    assert "Minor notice" in await _feed_titles(aclient)               # explicit opt-in wins


# ── end-to-end fetch wiring: english_guard, link normalize, per-source timeout ──
class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.headers = {"content-type": "application/rss+xml"}

    def raise_for_status(self):
        pass


class _FakeClient:
    def __init__(self, body):
        self._body = body
        self.calls = []

    async def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        return _FakeResp(self._body)


_GUARDED_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>PIB-like</title>
<item><title>Cabinet approves the semiconductor incentive scheme for fabs</title>
<link>https://www.sebi.gov.in/https://www.sebi.gov.in/notice/order-jul-2026.pdf</link>
<description>A sufficiently long description body for the snippet threshold to pass fine.</description></item>
<item><title>प्रधानमंत्री ने नई योजना का उद्घाटन किया</title>
<link>https://gov.example/hi/item2</link>
<description>Hindi item that the english guard must drop before it pollutes the corpus.</description></item>
</channel></rss>"""


async def test_fetch_single_feed_wires_guard_normalize_and_timeout(db_session):
    """End-to-end through fetch_single_feed: the flagged source drops the Hindi entry, stores the
    SEBI-style link NORMALIZED (dedup key sanity), and passes the per-source timeout to the client."""
    from app.services import fetcher

    src = Source(name="Guarded Official", url="https://guarded.example",
                 rss_url="https://guarded.example/rss", source_type=SourceType.official,
                 region="in", category="policy", credibility_score=95, audience=["policy"],
                 credibility_meta={"english_guard": True, "fetch_timeout": 45})
    db_session.add(src)
    await db_session.flush()

    client = _FakeClient(_GUARDED_RSS)
    new_count = await fetcher.fetch_single_feed(src, client, session=db_session)

    assert client.calls[0]["timeout"] == 45.0                     # [18] per-source timeout wired
    assert new_count == 1                                          # [5] Hindi entry dropped
    arts = (await db_session.execute(
        sa.select(Article).where(Article.source_id == src.id))).scalars().all()
    titles = {a.title for a in arts}
    assert any("semiconductor" in t for t in titles)
    assert not any("योजना" in t for t in titles)
    # [14] the stored URL is the normalized inner URL, applied after relative-URL resolution
    assert {a.url for a in arts} == {"https://www.sebi.gov.in/notice/order-jul-2026.pdf"}
