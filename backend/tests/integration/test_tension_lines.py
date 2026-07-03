"""#98 — discover tension-line lens + backfill (cached on extra_json, backfill-generated)."""
from datetime import datetime, timezone

import sqlalchemy as sa

from app.models import Article, ClusterArticle, Source, SourceType, StoryCluster
from app.services import lenses


async def _cluster(db_session, title="Regulators move on Big Tech"):
    src = Source(name="wire", url="https://wire.example", rss_url="https://wire.example/rss",
                 source_type=SourceType.wire, region="global", category="world")
    db_session.add(src)
    await db_session.flush()
    art = Article(title=title, url="https://wire.example/a1", source_id=src.id,
                  snippet="Antitrust regulators opened a probe into the platform's ad business.",
                  published_at=datetime(2026, 7, 4, tzinfo=timezone.utc))
    db_session.add(art)
    await db_session.flush()
    cl = StoryCluster(title=title, summary="s", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()
    return cl


def _stub_gen(line, counter):
    async def _gen(*a, **k):
        counter["n"] += 1
        return {"tension_line": line}
    return _gen


async def test_tension_line_generates_and_caches(db_session, monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(lenses.llm, "generate", _stub_gen("Regulators vs Big Tech: who blinks first", counter))
    cl = await _cluster(db_session)

    line = await lenses.tension_line(db_session, cl.id)
    assert line and "Regulators" in line and counter["n"] == 1

    again = await lenses.tension_line(db_session, cl.id)  # unchanged source_hash → cache hit
    assert again == line and counter["n"] == 1  # no second LLM call


async def test_backfill_generates_then_skips_unchanged(db_session, monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(lenses.llm, "generate", _stub_gen("A vs B over C", counter))
    await _cluster(db_session)

    await lenses.backfill_tension_lines(db_session)
    assert counter["n"] == 1
    await lenses.backfill_tension_lines(db_session)  # same source_hash
    assert counter["n"] == 1  # no regen


async def test_backfill_no_llm_key_is_noop(db_session, monkeypatch):
    async def _raise(*a, **k):
        raise lenses.llm.LLMUnavailable("no key")
    monkeypatch.setattr(lenses.llm, "generate", _raise)
    cl = await _cluster(db_session)

    await lenses.backfill_tension_lines(db_session)  # must not crash

    fresh = (await db_session.execute(sa.select(StoryCluster).where(StoryCluster.id == cl.id))).scalar_one()
    assert "tension" not in (fresh.extra_json or {})  # nothing cached without a key
