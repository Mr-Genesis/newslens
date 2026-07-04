"""WS-5 (#115): /stats gains impressions + CTR per surface (opens = read + interesting over the
surface-tagged impression log)."""
import pytest

from app.models import Article, FeedbackType, Impression, Source, SourceType, User, UserFeedback

_n = 0


async def _ensure_user(db, uid=1):
    if await db.get(User, uid) is None:
        db.add(User(id=uid, locale="IN"))
        await db.flush()


async def _article(db):
    global _n
    _n += 1
    src = Source(name="S", url=f"https://st/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    a = Article(title=f"a{_n}", url=f"https://st/{_n}/a", source_id=src.id)
    db.add(a)
    await db.flush()
    return a


@pytest.mark.asyncio
async def test_stats_reports_impressions_and_ctr_per_surface(aclient, db_session):
    await _ensure_user(db_session)
    arts = [await _article(db_session) for _ in range(3)]
    # 3 feed impressions (distinct articles → not deduped), 1 rail impression
    for a in arts:
        db_session.add(Impression(user_id=1, article_id=a.id, surface="feed"))
    db_session.add(Impression(user_id=1, article_id=arts[0].id, surface="rail"))
    # 2 feed OPENS (read + interesting) + 1 feed save (NOT an open)
    db_session.add(UserFeedback(user_id=1, article_id=arts[0].id, feedback_type=FeedbackType.read, surface="feed"))
    db_session.add(UserFeedback(user_id=1, article_id=arts[1].id, feedback_type=FeedbackType.interesting, surface="feed"))
    db_session.add(UserFeedback(user_id=1, article_id=arts[2].id, feedback_type=FeedbackType.save, surface="feed"))
    await db_session.flush()

    body = (await aclient.get("/stats")).json()
    surfaces = {s["surface"]: s for s in body["surfaces"]}

    assert surfaces["feed"]["impressions"] == 3
    assert surfaces["feed"]["clicks"] == 2                 # read + interesting; save excluded
    assert abs(surfaces["feed"]["ctr"] - 2 / 3) < 1e-6
    assert surfaces["rail"]["impressions"] == 1
    assert surfaces["rail"]["clicks"] == 0
    assert surfaces["rail"]["ctr"] == 0.0


@pytest.mark.asyncio
async def test_stats_surfaces_empty_without_impressions(aclient, db_session):
    await _ensure_user(db_session)
    body = (await aclient.get("/stats")).json()
    assert body["surfaces"] == []  # backward-compatible: no impressions → empty list, scalars intact
    assert "articles_read" in body
