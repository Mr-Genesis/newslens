"""Phase 2 · #82 — feed source-type filter (GET /feed?source_type=news|research|expert)."""
from datetime import datetime, timezone

import sqlalchemy as sa

from app.models import Article, Source, SourceType, User


async def _seed(db_session):
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = "Cardiologist"  # so the medicine-tagged research source is visible
    news = Source(name="Reuters", url="https://reuters.example", rss_url="https://reuters.example/rss",
                  source_type=SourceType.wire, region="global", category="world")
    research = Source(name="NEJM", url="https://nejm.example", rss_url="https://nejm.example/rss",
                      source_type=SourceType.research, region="global", category="research",
                      credibility_score=98, audience=["medicine"])
    db_session.add_all([news, research])
    await db_session.flush()
    db_session.add_all([
        Article(title="News item", url="https://reuters.example/a1", source_id=news.id,
                snippet="news snippet long enough here.", published_at=datetime(2026, 7, 3, tzinfo=timezone.utc)),
        Article(title="Research item", url="https://nejm.example/a1", source_id=research.id,
                snippet="research snippet long enough.", published_at=datetime(2026, 7, 3, 1, tzinfo=timezone.utc)),
    ])
    await db_session.flush()


async def _titles(aclient, qs=""):
    r = await aclient.get(f"/feed?per_page=50{qs}")
    assert r.status_code == 200
    return {a["title"] for a in r.json()["articles"]}


async def test_filter_research_returns_only_research(aclient, db_session):
    await _seed(db_session)
    t = await _titles(aclient, "&source_type=research")
    assert t == {"Research item"}


async def test_filter_news_excludes_gated(aclient, db_session):
    await _seed(db_session)
    t = await _titles(aclient, "&source_type=news")
    assert "News item" in t and "Research item" not in t


async def test_no_filter_returns_all_visible(aclient, db_session):
    await _seed(db_session)
    t = await _titles(aclient)  # doctor sees both
    assert {"News item", "Research item"} <= t


async def test_invalid_source_type_is_400(aclient, db_session):
    await _seed(db_session)
    r = await aclient.get("/feed?source_type=bogus")
    assert r.status_code == 400


async def test_source_type_filter_composes_with_follow_override(aclient, db_session):
    """A followed research source (opt-in past the gate) must still obey the type filter: it appears
    under ?source_type=research but NOT under ?source_type=news. Guards that the follow-override
    bypasses the persona gate WITHOUT bypassing the orthogonal source-type filter."""
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = None  # profession-less → research only visible via the follow
    news = Source(name="Reuters", url="https://reuters.example", rss_url="https://reuters.example/rss",
                  source_type=SourceType.wire, region="global", category="world")
    research = Source(name="NEJM", url="https://nejm.example", rss_url="https://nejm.example/rss",
                      source_type=SourceType.research, region="global", category="research",
                      credibility_score=98, audience=["medicine"])
    db_session.add_all([news, research])
    await db_session.flush()
    db_session.add_all([
        Article(title="News item", url="https://reuters.example/a1", source_id=news.id,
                snippet="news snippet long enough here.", published_at=datetime(2026, 7, 3, tzinfo=timezone.utc)),
        Article(title="Research item", url="https://nejm.example/a1", source_id=research.id,
                snippet="research snippet long enough.", published_at=datetime(2026, 7, 3, 1, tzinfo=timezone.utc)),
    ])
    await db_session.flush()
    await aclient.post("/follows", json={"kind": "source", "value": str(research.id)})

    assert await _titles(aclient, "&source_type=research") == {"Research item"}
    news_titles = await _titles(aclient, "&source_type=news")
    assert "News item" in news_titles and "Research item" not in news_titles  # follow ≠ filter bypass
