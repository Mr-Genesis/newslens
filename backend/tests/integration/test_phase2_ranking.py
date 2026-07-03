"""Phase 2 · #79 credibility-weighted feed ranking + #80 briefing bonus.

Behavior through /feed and /briefing. The credibility multiplier lives in the feed ranking blend
(UER path, the default); it nudges ordering within ×[0.9, 1.1] and can never drown fresher news.
"""
from datetime import datetime, timedelta, timezone

from app.models import Article, Source, SourceType, User


async def _expert(db_session, name, score, *, audience=("ai",)):
    s = Source(name=name, url=f"https://{name}.example", rss_url=f"https://{name}.example/rss",
               source_type=SourceType.expert, region="global", category="technology",
               credibility_score=score, audience=list(audience))
    db_session.add(s)
    await db_session.flush()
    return s


async def _article(db_session, source, title, when):
    a = Article(title=title, url=f"https://{source.name}.example/{title.replace(' ', '-')}",
                source_id=source.id, snippet="body text goes here for the card.", published_at=when)
    db_session.add(a)
    await db_session.flush()
    return a


async def _ai_engineer(db_session):
    u = (await db_session.execute(
        __import__("sqlalchemy").select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = "AI Engineer"
    await db_session.flush()


async def test_higher_credibility_ranks_first_at_equal_recency(aclient, db_session):
    await _ai_engineer(db_session)
    now = datetime(2026, 7, 3, 12, tzinfo=timezone.utc)
    high = await _expert(db_session, "highcred", 95)
    low = await _expert(db_session, "lowcred", 60)
    # Insert the HIGH-cred article FIRST (lower id) so the existing (recency, pub_ts, id-desc)
    # tiebreak actively works AGAINST it — only the credibility multiplier can put it on top.
    await _article(db_session, high, "High cred take", now)
    await _article(db_session, low, "Low cred take", now)  # higher id → wins id-desc tiebreak

    r = await aclient.get("/feed?per_page=20")
    assert r.status_code == 200
    titles = [a["title"] for a in r.json()["articles"]]
    assert titles.index("High cred take") < titles.index("Low cred take")


async def _news(db_session, name):
    s = Source(name=name, url=f"https://{name}.example", rss_url=f"https://{name}.example/rss",
               source_type=SourceType.wire, region="global", category="world")  # NULL credibility
    db_session.add(s)
    await db_session.flush()
    return s


async def test_credibility_cannot_drown_fresher_news(aclient, db_session):
    """The ±10% cap means a much fresher news story stays above an older max-credibility expert."""
    await _ai_engineer(db_session)
    now = datetime(2026, 7, 3, 12, tzinfo=timezone.utc)
    filler = await _news(db_session, "filler")   # sets the recency span floor
    await _article(db_session, filler, "Old filler", now - timedelta(hours=100))
    expert = await _expert(db_session, "topexpert", 98)
    await _article(db_session, expert, "Older expert analysis", now - timedelta(hours=10))
    news = await _news(db_session, "wire")
    await _article(db_session, news, "Breaking wire story", now)  # freshest, NULL credibility

    r = await aclient.get("/feed?per_page=20")
    titles = [a["title"] for a in r.json()["articles"]]
    assert titles.index("Breaking wire story") < titles.index("Older expert analysis")


async def test_credibility_score_over_100_is_clamped(aclient, db_session):
    """An out-of-range stored score (e.g. 150) is clamped to 100 → the ×[0.9,1.1] bound still holds,
    so a much fresher news story is NOT drowned. Without the clamp, ×1.2 would flip the order."""
    await _ai_engineer(db_session)
    now = datetime(2026, 7, 3, 12, tzinfo=timezone.utc)
    filler = await _news(db_session, "filler")
    await _article(db_session, filler, "Old filler", now - timedelta(hours=100))
    huge = await _expert(db_session, "overscored", 150)  # out of range; must be clamped
    await _article(db_session, huge, "Older over-scored take", now - timedelta(hours=10))
    news = await _news(db_session, "wire")
    await _article(db_session, news, "Breaking wire story", now)

    r = await aclient.get("/feed?per_page=20")
    titles = [a["title"] for a in r.json()["articles"]]
    assert titles.index("Breaking wire story") < titles.index("Older over-scored take")


async def test_audience_null_gated_source_gets_no_field_bonus(aclient, db_session, fake_llm):
    """The +0.15 bonus requires a real audience match. A general (audience-null) research source is
    visible to everyone but is NOT "your field" → no bonus → it does not jump the fresher news."""
    await _set_profession(db_session, None)  # profession-less
    base = datetime(2026, 7, 3, 12, tzinfo=timezone.utc)
    general = Source(name="Quanta", url="https://quanta.example", rss_url="https://quanta.example/rss",
                     source_type=SourceType.research, region="global", category="research",
                     credibility_score=90, audience=None)  # audience-null → shown to all, no field match
    db_session.add(general)
    await db_session.flush()
    await _cluster(db_session, general, "General science piece", base - timedelta(hours=100))  # oldest
    for i in range(8):
        news = await _news(db_session, f"news{i}")
        await _cluster(db_session, news, f"World story {i}", base - timedelta(hours=i))

    r = await aclient.get("/briefing")
    titles = {s["title"] for s in r.json()["stories"]}
    assert "General science piece" not in titles  # no bonus → stays dropped as the oldest


# ── #80 briefing bonus ──
async def _cluster(db_session, source, title, created_at):
    from app.models import ClusterArticle, StoryCluster
    art = Article(title=title, url=f"https://{source.name}.example/{title.replace(' ', '-')}",
                  source_id=source.id, snippet="A sufficiently long snippet for the story card body.",
                  published_at=created_at)
    db_session.add(art)
    await db_session.flush()
    cl = StoryCluster(title=title, summary="Cached summary so the briefing skips the LLM.",
                      coherence=0.9, created_at=created_at)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()
    return cl


async def _set_profession(db_session, profession):
    import sqlalchemy as sa
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = profession
    await db_session.flush()


async def test_matched_research_cluster_makes_briefing_top8(aclient, db_session, fake_llm):
    """A cardiologist's cardiology paper reaches the top-8 even as the OLDEST cluster, because the
    persona-match bonus lifts it past 8 fresher news clusters (without the bonus it is dropped)."""
    await _set_profession(db_session, "Cardiologist")
    base = datetime(2026, 7, 3, 12, tzinfo=timezone.utc)
    nejm = Source(name="NEJM", url="https://nejm.example", rss_url="https://nejm.example/rss",
                  source_type=SourceType.research, region="global", category="research",
                  credibility_score=98, audience=["medicine"])
    db_session.add(nejm)
    await db_session.flush()
    # Oldest cluster of the nine → without the bonus it sorts to position 9 and is dropped.
    await _cluster(db_session, nejm, "New cardiology trial", base - timedelta(hours=100))
    for i in range(8):  # 8 fresher news clusters
        news = await _news(db_session, f"news{i}")
        await _cluster(db_session, news, f"World story {i}", base - timedelta(hours=i))

    r = await aclient.get("/briefing")
    assert r.status_code == 200
    stories = r.json()["stories"]
    by_title = {s["title"]: s for s in stories}
    assert "New cardiology trial" in by_title
    # #78: the API exposes the gated tier for the badge; news stories carry no tier.
    assert by_title["New cardiology trial"]["tier"] == "research"
    assert all(s["tier"] is None for s in stories if s["title"].startswith("World story"))
