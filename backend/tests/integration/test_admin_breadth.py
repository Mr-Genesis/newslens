"""#97 — GET /admin/breadth: source-diversity + coverage + staleness metrics."""
from datetime import datetime, timedelta, timezone

from app.models import Article, ArticleTopic, Source, SourceType, Topic


async def _src(db_session, name, source_type, *, region="global", gated_score=None):
    s = Source(name=name, url=f"https://{name}.example", rss_url=f"https://{name}.example/rss",
               source_type=source_type, region=region, category="world",
               credibility_score=gated_score,
               audience=["medicine"] if gated_score is not None else None)
    db_session.add(s)
    await db_session.flush()
    return s


async def _articles(db_session, source, n, *, fetched):
    for i in range(n):
        db_session.add(Article(title=f"{source.name}-{i}", url=f"https://{source.name}.example/{i}",
                               source_id=source.id, snippet="body", fetched_at=fetched,
                               published_at=fetched))
    await db_session.flush()


async def test_admin_breadth_reports_diversity_coverage_staleness(aclient, db_session):
    now = datetime(2026, 7, 4, 12, tzinfo=timezone.utc)
    news1 = await _src(db_session, "wirey", SourceType.wire)
    news2 = await _src(db_session, "newsy", SourceType.newspaper, region="in")   # zero articles
    research = await _src(db_session, "nejm", SourceType.research, gated_score=98)
    expert = await _src(db_session, "strat", SourceType.expert, gated_score=88)   # stale
    await _articles(db_session, news1, 3, fetched=now - timedelta(hours=1))
    await _articles(db_session, research, 1, fetched=now - timedelta(hours=2))
    await _articles(db_session, expert, 1, fetched=now - timedelta(days=40))      # older than 30d

    # a topic covering the wire articles
    topic = Topic(name="World")
    db_session.add(topic)
    await db_session.flush()
    arts = (await db_session.execute(
        __import__("sqlalchemy").select(Article).where(Article.source_id == news1.id))).scalars().all()
    for a in arts:
        db_session.add(ArticleTopic(article_id=a.id, topic_id=topic.id))
    await db_session.flush()

    r = await aclient.get("/admin/breadth?days=30")
    assert r.status_code == 200
    b = r.json()

    assert b["sources"]["by_type"]["wire"] == 1 and b["sources"]["by_type"]["research"] == 1
    assert b["sources"]["by_type"]["expert"] == 1 and b["sources"]["by_type"]["newspaper"] == 1
    assert b["sources"]["by_region"]["in"] == 1
    assert b["sources"]["gated"] == 2 and b["sources"]["total"] == 4
    assert b["articles"]["total"] == 5

    aps = b["articles_per_source"]
    assert aps["top"][0]["count"] == 3 and aps["top"][0]["name"] == "wirey"   # leaderboard sorted desc
    assert aps["zero_article_sources"] == 1                                    # newsy

    topics = {t["name"]: t["count"] for t in b["articles_per_topic"]}
    assert topics.get("World") == 3

    stale_names = {s["name"] for s in b["stale_sources"]}
    assert "strat" in stale_names          # last article 40d ago > 30d window
    assert "wirey" not in stale_names       # fresh


async def test_admin_breadth_days_param_widens_window(aclient, db_session):
    now = datetime(2026, 7, 4, 12, tzinfo=timezone.utc)
    expert = await _src(db_session, "strat", SourceType.expert, gated_score=88)
    await _articles(db_session, expert, 1, fetched=now - timedelta(days=40))

    stale_30 = {s["name"] for s in (await aclient.get("/admin/breadth?days=30")).json()["stale_sources"]}
    stale_90 = {s["name"] for s in (await aclient.get("/admin/breadth?days=90")).json()["stale_sources"]}
    assert "strat" in stale_30 and "strat" not in stale_90   # 40d: stale at 30, fresh at 90
