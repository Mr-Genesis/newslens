"""Phase 2 · #83 — discover deck is the opt-in surface for the gated tiers.

Up to ~5 of the ~25 cards are research/expert regardless of profession match, each flagged so the
UI can badge them and offer "Follow source". The rest of the deck is news (non-gated).
"""
from datetime import datetime, timezone

import sqlalchemy as sa

from app.models import Article, Source, SourceType, User


async def _profession_less(db_session):
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = None
    await db_session.flush()


async def _src_with_article(db_session, name, source_type, title, **kw):
    s = Source(name=name, url=f"https://{name}.example", rss_url=f"https://{name}.example/rss",
               source_type=source_type, region="global", category=kw.pop("category", "world"), **kw)
    db_session.add(s)
    await db_session.flush()
    db_session.add(Article(title=title, url=f"https://{name}.example/a1", source_id=s.id,
                           snippet="A snippet long enough to build the discover card facts here.",
                           published_at=datetime(2026, 7, 3, tzinfo=timezone.utc)))
    await db_session.flush()
    return s


async def test_deck_surfaces_gated_sources_as_optin(aclient, db_session):
    await _profession_less(db_session)
    for i in range(3):
        await _src_with_article(db_session, f"news{i}", SourceType.wire, f"News {i}")
    await _src_with_article(db_session, "NEJM", SourceType.research, "Cardiology paper",
                            category="research", credibility_score=98, audience=["medicine"], is_preprint=False)
    await _src_with_article(db_session, "arXiv", SourceType.research, "AI preprint",
                            category="research", credibility_score=80, audience=["ai"], is_preprint=True)

    resp = await aclient.get("/discover/deck")
    assert resp.status_code == 200
    cards = resp.json()
    gated = [c for c in cards if c["is_gated"]]
    assert 1 <= len(gated) <= 5                                   # opt-in surfacing, capped
    assert all(c["source_type"] in ("research", "expert") for c in gated)
    assert all(c["source_id"] for c in gated)                    # frontend can POST a source-follow
    # The main pool is news-only → a non-gated card is never a research/expert source.
    nongated = [c for c in cards if not c["is_gated"]]
    assert all(c["source_type"] not in ("research", "expert") for c in nongated)
    # Preprint flag rides along for the badge.
    assert any(c["is_preprint"] for c in gated if c["title"] == "AI preprint")


async def test_gated_slots_capped_at_five(aclient, db_session):
    """With more gated sources than the cap, the deck admits exactly discover_gated_slots (5) of
    them; the remaining ~20 cards are all non-gated news. Guards the LIMIT against a silent widening."""
    await _profession_less(db_session)
    for i in range(8):  # 8 gated sources > the cap of 5
        await _src_with_article(db_session, f"journal{i}", SourceType.research, f"Paper {i}",
                                category="research", credibility_score=90, audience=["medicine"])
    for i in range(10):  # plenty of news to fill the rest
        await _src_with_article(db_session, f"news{i}", SourceType.wire, f"News {i}")

    cards = (await aclient.get("/discover/deck")).json()
    gated = [c for c in cards if c["is_gated"]]
    assert len(gated) == 5  # exactly the cap, not all 8
    assert all(c["source_type"] not in ("research", "expert") for c in cards if not c["is_gated"])


async def test_deck_is_all_news_when_no_gated_sources(aclient, db_session):
    """No research/expert sources at all → a full, non-empty news deck (the 25 - 0 split is valid)."""
    await _profession_less(db_session)
    for i in range(6):
        await _src_with_article(db_session, f"news{i}", SourceType.wire, f"News {i}")

    cards = (await aclient.get("/discover/deck")).json()
    assert len(cards) == 6
    assert all(not c["is_gated"] for c in cards)
