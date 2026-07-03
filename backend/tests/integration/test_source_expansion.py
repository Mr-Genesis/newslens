"""Phase 1 source expansion: research/expert tiers, credibility, persona gating.

Behavior-level tests through the public surfaces (ORM persistence, ensure_sources,
audience mapping, /feed + /briefing gating, /admin/sources validation).
"""
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Article, Source, SourceType, User


async def _seed_news_and_research(db_session):
    """A plain news source + a medicine-gated research source, each with one article."""
    news = Source(name="Reuters", url="https://reuters.example", rss_url="https://reuters.example/rss",
                  source_type=SourceType.wire, region="global", category="world")
    research = Source(name="NEJM", url="https://nejm.example", rss_url="https://nejm.example/rss",
                      source_type=SourceType.research, region="global", category="research",
                      credibility_score=98, audience=["medicine"], is_preprint=False)
    db_session.add_all([news, research])
    await db_session.flush()
    db_session.add_all([
        Article(title="Markets rally", url="https://reuters.example/a1", source_id=news.id,
                snippet="stocks up", published_at=datetime(2026, 7, 3, tzinfo=timezone.utc)),
        Article(title="New cardiology trial", url="https://nejm.example/a1", source_id=research.id,
                snippet="trial results", published_at=datetime(2026, 7, 3, 1, tzinfo=timezone.utc)),
    ])
    await db_session.flush()


async def _set_profession(db_session, profession):
    u = (await db_session.execute(select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = profession
    await db_session.flush()


async def test_source_supports_expert_tier_with_credibility(db_session):
    """A source can be an expert/research tier with a credibility score + audience tags."""
    db_session.add(
        Source(
            name="One Useful Thing",
            url="https://oneusefulthing.org",
            rss_url="https://oneusefulthing.org/feed",
            source_type=SourceType.expert,
            author_name="Ethan Mollick",
            credibility_score=92,
            credibility_meta={"affiliation": "Wharton", "reviewed_by": "seed"},
            audience=["ai", "software"],
            is_preprint=False,
        )
    )
    await db_session.flush()

    s = (
        await db_session.execute(select(Source).where(Source.name == "One Useful Thing"))
    ).scalar_one()
    assert s.source_type is SourceType.expert
    assert s.credibility_score == 92
    assert s.author_name == "Ethan Mollick"
    assert s.audience == ["ai", "software"]
    assert s.credibility_meta["reviewed_by"] == "seed"
    assert s.is_preprint is False


async def test_research_gated_out_for_profession_less_user(aclient, db_session):
    """A profession-less user's feed excludes research/expert sources (byte-identical behaviour)."""
    await _seed_news_and_research(db_session)
    await _set_profession(db_session, None)

    r = await aclient.get("/feed?per_page=50")
    assert r.status_code == 200
    titles = {a["title"] for a in r.json()["articles"]}
    assert "Markets rally" in titles
    assert "New cardiology trial" not in titles  # gated out


async def test_research_shown_to_matching_profession(aclient, db_session):
    """A doctor sees the medicine-tagged research source."""
    await _seed_news_and_research(db_session)
    await _set_profession(db_session, "Cardiologist")

    r = await aclient.get("/feed?per_page=50")
    titles = {a["title"] for a in r.json()["articles"]}
    assert "Markets rally" in titles
    assert "New cardiology trial" in titles  # persona match


async def test_below_feed_floor_excluded_even_when_matching(aclient, db_session):
    """A low-credibility expert (below the feed floor) is discover-only — never in the feed,
    even for a user whose profession matches its audience."""
    low = Source(name="Zvi", url="https://thezvi.example", rss_url="https://thezvi.example/rss",
                 source_type=SourceType.expert, region="global", category="ai",
                 credibility_score=54, audience=["ai"])  # 54 < feed floor 55
    db_session.add(low)
    await db_session.flush()
    db_session.add(Article(title="AI roundup", url="https://thezvi.example/a1", source_id=low.id,
                           snippet="weekly", published_at=datetime(2026, 7, 3, tzinfo=timezone.utc)))
    await db_session.flush()
    await _set_profession(db_session, "AI Engineer")

    r = await aclient.get("/feed?per_page=50")
    titles = {a["title"] for a in r.json()["articles"]}
    assert "AI roundup" not in titles


async def _cluster_with_article(db_session, source, title, url):
    from app.models import StoryCluster, ClusterArticle
    art = Article(title=title, url=url, source_id=source.id, snippet="body text here.",
                  published_at=datetime(2026, 7, 3, tzinfo=timezone.utc))
    db_session.add(art)
    await db_session.flush()
    cl = StoryCluster(title=title, summary="s", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()
    return cl


async def test_briefing_gates_research_cluster(aclient, db_session, fake_llm):
    news = Source(name="BBC", url="https://bbc.example", rss_url="https://bbc.example/rss",
                  source_type=SourceType.wire, region="global", category="world")
    research = Source(name="NEJM", url="https://nejm.example", rss_url="https://nejm.example/rss",
                      source_type=SourceType.research, region="global", category="research",
                      credibility_score=98, audience=["medicine"])
    db_session.add_all([news, research])
    await db_session.flush()
    await _cluster_with_article(db_session, news, "World news story", "https://bbc.example/a1")
    await _cluster_with_article(db_session, research, "Cardiology paper", "https://nejm.example/a1")

    await _set_profession(db_session, None)
    r1 = await aclient.get("/briefing")
    t1 = {s["title"] for s in r1.json()["stories"]}
    assert "World news story" in t1 and "Cardiology paper" not in t1

    await _set_profession(db_session, "Cardiologist")
    r2 = await aclient.get("/briefing")
    t2 = {s["title"] for s in r2.json()["stories"]}
    assert "Cardiology paper" in t2


async def test_upsert_sets_new_tier_fields(db_session):
    from app.services import fetcher
    feed = {
        "name": "Ground Truths", "url": "https://erictopol.substack.com",
        "rss_url": "https://erictopol.substack.com/feed", "is_paywalled": False,
        "source_type": "expert", "region": "global", "category": "research",
        "author_name": "Eric Topol", "credibility_score": 95, "audience": ["medicine"],
        "is_preprint": False, "per_fetch_cap": 10,
    }
    await fetcher._upsert_sources(db_session, [feed])
    s = (await db_session.execute(
        select(Source).where(Source.url == "https://erictopol.substack.com"))).scalar_one()
    assert s.source_type is SourceType.expert
    assert s.credibility_score == 95 and s.author_name == "Eric Topol"
    assert s.audience == ["medicine"] and s.per_fetch_cap == 10


async def test_upsert_does_not_clobber_admin_reviewed_credibility(db_session):
    """A human-reviewed credibility score is locked against the 10-min sources.json re-upsert."""
    from app.services import fetcher
    db_session.add(Source(
        name="Stratechery", url="https://stratechery.com", rss_url="https://stratechery.com/feed",
        source_type=SourceType.expert, credibility_score=88, author_name="Ben Thompson",
        credibility_meta={"reviewed_by": "admin"}, audience=["ai", "business"]))
    await db_session.flush()
    # sources.json ships a DIFFERENT seed score for the same url
    feed = {"name": "Stratechery", "url": "https://stratechery.com",
            "rss_url": "https://stratechery.com/feed", "source_type": "expert",
            "credibility_score": 82, "audience": ["ai"], "region": "global", "category": "research"}
    await fetcher._upsert_sources(db_session, [feed])
    s = (await db_session.execute(
        select(Source).where(Source.url == "https://stratechery.com"))).scalar_one()
    assert s.credibility_score == 88  # admin value preserved, not clobbered to 82
    assert s.audience == ["ai", "business"]


async def test_admin_create_expert_requires_credibility(aclient):
    """You can't publish an expert/research source without a credibility score — the whole point
    of the tier is that unvetted voices don't get in. Missing score ⇒ 400."""
    r = await aclient.post("/admin/sources", json={
        "name": "Random Blog", "url": "https://randomblog.example",
        "source_type": "expert",  # no credibility_score
    })
    assert r.status_code == 400


async def test_admin_create_expert_with_credibility_persists_tier_fields(aclient, db_session):
    """A well-formed expert source persists its tier fields and is stamped admin-reviewed."""
    r = await aclient.post("/admin/sources", json={
        "name": "Construction Physics", "url": "https://constructionphysics.example",
        "rss_url": "https://constructionphysics.example/feed",
        "source_type": "expert", "author_name": "Brian Potter",
        "credibility_score": 84, "audience": ["science", "business"],
    })
    assert r.status_code == 200
    s = (await db_session.execute(
        select(Source).where(Source.url == "https://constructionphysics.example"))).scalar_one()
    assert s.source_type is SourceType.expert
    assert s.credibility_score == 84 and s.author_name == "Brian Potter"
    assert s.audience == ["science", "business"]
    assert (s.credibility_meta or {}).get("reviewed_by") == "admin"  # human-published ⇒ locked
