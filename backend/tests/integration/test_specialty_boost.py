"""#94 — per-specialty PubMed ranking boost (keeps the broad `medicine` gate)."""
from datetime import datetime, timezone

import sqlalchemy as sa

from app.models import Article, Source, SourceType, User


async def _specialty_source(db_session, name, specialty):
    s = Source(name=name, url=f"https://{name}.example", rss_url=f"https://{name}.example/rss",
               source_type=SourceType.research, region="global", category="research",
               credibility_score=90, audience=["medicine"],
               credibility_meta={"reviewed_by": "seed", "specialty": specialty})
    db_session.add(s)
    await db_session.flush()
    return s


async def _article(db_session, source, title, when):
    a = Article(title=title, url=f"https://{source.name}.example/{title.replace(' ', '-')}",
                source_id=source.id, snippet="A sufficiently long snippet for the card body.", published_at=when)
    db_session.add(a)
    await db_session.flush()
    return a


async def _profession(db_session, profession):
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = profession
    await db_session.flush()


async def test_own_specialty_ranks_above_other_specialty(aclient, db_session):
    now = datetime(2026, 7, 4, 12, tzinfo=timezone.utc)
    cardio = await _specialty_source(db_session, "cardiosrc", "cardiology")
    onco = await _specialty_source(db_session, "oncosrc", "oncology")
    # cardio inserted FIRST (lower id) so the (recency, id-desc) tiebreak works AGAINST it —
    # only the specialty boost can put it on top.
    await _article(db_session, cardio, "Cardiology paper", now)
    await _article(db_session, onco, "Oncology paper", now)

    await _profession(db_session, "Cardiologist")
    titles = [a["title"] for a in (await aclient.get("/feed?per_page=20")).json()["articles"]]
    assert titles.index("Cardiology paper") < titles.index("Oncology paper")


async def test_boost_is_specialty_specific(aclient, db_session):
    now = datetime(2026, 7, 4, 12, tzinfo=timezone.utc)
    cardio = await _specialty_source(db_session, "cardiosrc", "cardiology")
    onco = await _specialty_source(db_session, "oncosrc", "oncology")
    # onco inserted first (lower id); an oncologist must lift ITS paper over cardiology.
    await _article(db_session, onco, "Oncology paper", now)
    await _article(db_session, cardio, "Cardiology paper", now)

    await _profession(db_session, "Oncologist")
    titles = [a["title"] for a in (await aclient.get("/feed?per_page=20")).json()["articles"]]
    assert titles.index("Oncology paper") < titles.index("Cardiology paper")
