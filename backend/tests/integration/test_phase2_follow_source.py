"""Phase 2 · #81 — follow a source to opt in past the persona gate.

`follows.kind="source"` (value = source id). A followed source bypasses BOTH the audience match and
the credibility floor (explicit opt-in = explicit intent), in the feed and the briefing.
"""
from datetime import datetime, timezone

import sqlalchemy as sa

from app.models import Article, Source, SourceType, User


async def _gated(db_session, name, score, audience, source_type=SourceType.research):
    s = Source(name=name, url=f"https://{name}.example", rss_url=f"https://{name}.example/rss",
               source_type=source_type, region="global", category="research",
               credibility_score=score, audience=list(audience))
    db_session.add(s)
    await db_session.flush()
    db_session.add(Article(title=f"{name} story", url=f"https://{name}.example/a1", source_id=s.id,
                           snippet="A long enough snippet for the card body text here.",
                           published_at=datetime(2026, 7, 3, tzinfo=timezone.utc)))
    await db_session.flush()
    return s


async def _profession_less(db_session):
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = None
    await db_session.flush()


async def _feed_titles(aclient):
    r = await aclient.get("/feed?per_page=50")
    assert r.status_code == 200
    return {a["title"] for a in r.json()["articles"]}


async def test_following_a_source_reveals_it_in_feed(aclient, db_session):
    await _profession_less(db_session)
    nejm = await _gated(db_session, "NEJM", 98, ["medicine"])

    assert "NEJM story" not in await _feed_titles(aclient)  # gated out for a non-doctor

    r = await aclient.post("/follows", json={"kind": "source", "value": str(nejm.id)})
    assert r.status_code == 201

    assert "NEJM story" in await _feed_titles(aclient)  # follow bypasses the gate


async def test_unfollowing_reverts_the_gate(aclient, db_session):
    await _profession_less(db_session)
    nejm = await _gated(db_session, "NEJM", 98, ["medicine"])
    fid = (await aclient.post("/follows", json={"kind": "source", "value": str(nejm.id)})).json()["id"]
    assert "NEJM story" in await _feed_titles(aclient)

    assert (await aclient.delete(f"/follows/{fid}")).status_code == 204
    assert "NEJM story" not in await _feed_titles(aclient)  # gate restored


async def test_follow_overrides_the_credibility_floor(aclient, db_session):
    """A followed source below the feed floor (Zvi at 54) still appears — explicit opt-in wins."""
    await _profession_less(db_session)
    zvi = await _gated(db_session, "Zvi", 54, ["ai"], source_type=SourceType.expert)  # 54 < floor 55
    assert "Zvi story" not in await _feed_titles(aclient)

    await aclient.post("/follows", json={"kind": "source", "value": str(zvi.id)})
    assert "Zvi story" in await _feed_titles(aclient)


async def test_follow_reveals_in_briefing(aclient, db_session, fake_llm):
    from app.models import ClusterArticle, StoryCluster
    await _profession_less(db_session)
    nejm = await _gated(db_session, "NEJM", 98, ["medicine"])
    art = (await db_session.execute(sa.select(Article).where(Article.source_id == nejm.id))).scalar_one()
    cl = StoryCluster(title="NEJM story", summary="cached summary", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()

    t0 = {s["title"] for s in (await aclient.get("/briefing")).json()["stories"]}
    assert "NEJM story" not in t0

    await aclient.post("/follows", json={"kind": "source", "value": str(nejm.id)})
    t1 = {s["title"] for s in (await aclient.get("/briefing")).json()["stories"]}
    assert "NEJM story" in t1


async def test_source_follow_nonexistent_returns_404(aclient, db_session):
    await _profession_less(db_session)
    r = await aclient.post("/follows", json={"kind": "source", "value": "999999"})
    assert r.status_code == 404


async def test_source_follow_non_integer_value_is_400(aclient, db_session):
    await _profession_less(db_session)
    r = await aclient.post("/follows", json={"kind": "source", "value": "not-a-number"})
    assert r.status_code == 400  # a source-follow value must be a source id


async def test_unfollow_reverts_the_briefing_gate(aclient, db_session, fake_llm):
    """The briefing must symmetrically restore the gate on unfollow (not just the feed)."""
    from app.models import ClusterArticle, StoryCluster
    await _profession_less(db_session)
    nejm = await _gated(db_session, "NEJM", 98, ["medicine"])
    art = (await db_session.execute(sa.select(Article).where(Article.source_id == nejm.id))).scalar_one()
    cl = StoryCluster(title="NEJM story", summary="cached summary", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()

    fid = (await aclient.post("/follows", json={"kind": "source", "value": str(nejm.id)})).json()["id"]
    assert "NEJM story" in {s["title"] for s in (await aclient.get("/briefing")).json()["stories"]}

    assert (await aclient.delete(f"/follows/{fid}")).status_code == 204
    assert "NEJM story" not in {s["title"] for s in (await aclient.get("/briefing")).json()["stories"]}


async def test_briefing_fallback_path_still_gates_gated_sources(aclient, db_session, fake_llm):
    """Regression guard for the fallback-leak fix: with NO clusters at all, the briefing's
    article-fallback must still hide a gated source from a non-matching user — and reveal it on
    follow. Without the `_allowed` gate on the fallback query, the research article would leak."""
    await _profession_less(db_session)
    nejm = await _gated(db_session, "NEJM", 98, ["medicine"])  # article, no cluster

    t0 = {s["title"] for s in (await aclient.get("/briefing")).json()["stories"]}
    assert "NEJM story" not in t0  # fallback is gated → no leak

    await aclient.post("/follows", json={"kind": "source", "value": str(nejm.id)})
    t1 = {s["title"] for s in (await aclient.get("/briefing")).json()["stories"]}
    assert "NEJM story" in t1  # follow reveals it even through the fallback path
