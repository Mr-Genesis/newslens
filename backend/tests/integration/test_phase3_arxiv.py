"""Phase 3 · #87 — arXiv-by-interest generation (idempotent) + visibility to a matching user."""
from datetime import datetime, timezone

import sqlalchemy as sa

from app.models import Article, Source, SourceType, Topic, User, UserPreference
from app.services import arxiv_gen


async def _interest(db_session, name):
    t = Topic(name=name)
    db_session.add(t)
    await db_session.flush()
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    await db_session.flush()
    db_session.add(UserPreference(user_id=1, topic_id=t.id, weight=1.0))
    await db_session.flush()
    return u


async def test_generate_arxiv_sources_from_interests_is_idempotent(db_session):
    await _interest(db_session, "Computer Vision")

    created = await arxiv_gen.generate_arxiv_sources(db_session)  # gathers from user prefs
    assert created == 1

    src = (await db_session.execute(
        sa.select(Source).where(Source.rss_url == "https://rss.arxiv.org/rss/cs.CV"))).scalar_one()
    assert src.source_type is SourceType.research and src.is_preprint is True
    assert set(src.audience) == {"ai", "technology"} and src.per_fetch_cap == 25

    again = await arxiv_gen.generate_arxiv_sources(db_session)
    assert again == 0  # existing source untouched


async def test_generated_arxiv_source_is_visible_to_matching_user(aclient, db_session):
    u = await _interest(db_session, "Computer Vision")
    u.profession = "AI Engineer"  # tags include ai/technology → clears the gate for cs.CV
    await db_session.flush()
    await arxiv_gen.generate_arxiv_sources(db_session)

    src = (await db_session.execute(
        sa.select(Source).where(Source.rss_url == "https://rss.arxiv.org/rss/cs.CV"))).scalar_one()
    db_session.add(Article(title="A vision preprint", url="https://arxiv.org/abs/2607.00001",
                           source_id=src.id, snippet="A convolutional architecture with strong results.",
                           published_at=datetime(2026, 7, 3, tzinfo=timezone.utc)))
    await db_session.flush()

    titles = {a["title"] for a in (await aclient.get("/feed?per_page=50")).json()["articles"]}
    assert "A vision preprint" in titles


async def test_generate_arxiv_no_interests_is_noop(db_session):
    created = await arxiv_gen.generate_arxiv_sources(db_session, interests=["Cooking", "Gardening"])
    assert created == 0
