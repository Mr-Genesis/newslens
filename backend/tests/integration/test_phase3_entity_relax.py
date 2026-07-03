"""Phase 3 · #89 — relax entity-extraction eligibility to 1 source for research-tier clusters."""
from datetime import datetime, timezone

from app.models import Article, ClusterArticle, Source, SourceType, StoryCluster
from app.services import entities


async def _cluster(db_session, source, title):
    art = Article(title=title, url=f"https://{source.name}.example/{title.replace(' ', '-')}",
                  source_id=source.id, snippet="body text here.",
                  published_at=datetime(2026, 7, 3, tzinfo=timezone.utc))
    db_session.add(art)
    await db_session.flush()
    cl = StoryCluster(title=title, summary="s", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()
    return cl, art


async def _source(db_session, name, source_type, **kw):
    s = Source(name=name, url=f"https://{name}.example", rss_url=f"https://{name}.example/rss",
               source_type=source_type, region="global", category=kw.pop("category", "world"), **kw)
    db_session.add(s)
    await db_session.flush()
    return s


async def test_research_singleton_is_extraction_candidate(db_session):
    research = await _source(db_session, "NEJM", SourceType.research, category="research",
                             credibility_score=98, audience=["medicine"])
    cl, _ = await _cluster(db_session, research, "A lone research paper")

    candidates = await entities._extraction_candidates(db_session)
    assert cl.id in candidates  # a single research source is enough


async def test_news_singleton_is_not_a_candidate(db_session):
    wire = await _source(db_session, "Reuters", SourceType.wire)
    cl, _ = await _cluster(db_session, wire, "A lone news item")

    candidates = await entities._extraction_candidates(db_session)
    assert cl.id not in candidates  # news still needs the min-2 "settled" bar


async def test_two_source_news_cluster_is_a_candidate(db_session):
    a = await _source(db_session, "BBC", SourceType.wire)
    b = await _source(db_session, "Guardian", SourceType.newspaper)
    art_a = Article(title="Shared story", url="https://bbc.example/x", source_id=a.id,
                    snippet="b", published_at=datetime(2026, 7, 3, tzinfo=timezone.utc))
    art_b = Article(title="Shared story", url="https://guardian.example/x", source_id=b.id,
                    snippet="b", published_at=datetime(2026, 7, 3, tzinfo=timezone.utc))
    db_session.add_all([art_a, art_b])
    await db_session.flush()
    cl = StoryCluster(title="Shared story", summary="s", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add_all([ClusterArticle(cluster_id=cl.id, article_id=art_a.id),
                        ClusterArticle(cluster_id=cl.id, article_id=art_b.id)])
    await db_session.flush()

    candidates = await entities._extraction_candidates(db_session)
    assert cl.id in candidates


async def test_expert_singleton_is_not_a_candidate(db_session):
    """The relax is research-only — a lone expert/Substack cluster still needs the min-2 bar."""
    expert = await _source(db_session, "Stratechery", SourceType.expert, category="technology",
                           credibility_score=88, audience=["ai"])
    cl, _ = await _cluster(db_session, expert, "A lone expert post")

    candidates = await entities._extraction_candidates(db_session)
    assert cl.id not in candidates
