"""#103 — discover deck serves the cached tension line, falling back to the article title."""
from datetime import datetime, timezone

from app.models import Article, ClusterArticle, Source, SourceType, StoryCluster
from app.services import lenses


async def _news(db_session, name):
    s = Source(name=name, url=f"https://{name}.example", rss_url=f"https://{name}.example/rss",
               source_type=SourceType.wire, region="global", category="world")
    db_session.add(s)
    await db_session.flush()
    return s


async def _article(db_session, source, title):
    a = Article(title=title, url=f"https://{source.name}.example/{title.replace(' ', '-')}",
                source_id=source.id, snippet="A long enough snippet to build the discover facts here.",
                published_at=datetime(2026, 7, 4, tzinfo=timezone.utc))
    db_session.add(a)
    await db_session.flush()
    return a


async def test_deck_uses_cached_tension_line_else_title(aclient, db_session, monkeypatch):
    # Article A → clustered with a cached tension line; Article B → no cluster, no tension.
    sa_src = await _news(db_session, "srca")
    a = await _article(db_session, sa_src, "Clustered story")
    cl = StoryCluster(title="Clustered story", summary="s", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db_session.flush()

    sb_src = await _news(db_session, "srcb")
    b = await _article(db_session, sb_src, "Lonely story")

    # populate the tension cache for A's cluster (via a stubbed LLM)
    async def _gen(*args, **kw):
        return {"tension_line": "Agencies vs the platform over ad dominance"}
    monkeypatch.setattr(lenses.llm, "generate", _gen)
    await lenses.tension_line(db_session, cl.id)

    cards = (await aclient.get("/discover/deck")).json()
    by_title = {c["title"]: c for c in cards}
    assert by_title["Clustered story"]["tension_line"] == "Agencies vs the platform over ad dominance"
    assert by_title["Lonely story"]["tension_line"] == "Lonely story"  # title fallback
