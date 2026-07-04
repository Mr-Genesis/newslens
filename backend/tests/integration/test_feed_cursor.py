"""WS-3 (#113): the as_of pagination cursor. Pins the feed pool to fetched_at <= as_of so new
ingest mid-scroll can't duplicate/drop rows across a page boundary — on BOTH the personalized and
legacy paths. First response echoes as_of=now; a stale cursor (empty window) recovers with a fresh
cursor + empty items."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Article, EmbeddingStatus, Source, SourceType, User

UTC = timezone.utc
_seq = 0


async def _ensure_user1(db):
    if (await db.execute(select(User).where(User.id == 1))).scalar_one_or_none() is None:
        db.add(User(id=1, locale="IN"))
        await db.flush()


async def _src(db):
    global _seq
    _seq += 1
    s = Source(name="S", url=f"https://cur/{_seq}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _article_at(db, src, *, published, fetched, title):
    """Seed an article with EXPLICIT fetched_at (the cursor axis) and published_at (the sort axis)."""
    global _seq
    _seq += 1
    a = Article(title=title, url=f"https://cur/{_seq}/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete, published_at=published, fetched_at=fetched)
    db.add(a)
    await db.flush()
    return a


@pytest.mark.asyncio
async def test_first_response_echoes_as_of_now(aclient, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", False)
    src = await _src(db_session)
    now = datetime.now(UTC)
    await _article_at(db_session, src, published=now, fetched=now, title="A")
    await db_session.flush()

    body = (await aclient.get("/feed?per_page=50")).json()
    assert "as_of" in body, "feed response must carry the pagination cursor"
    returned = datetime.fromisoformat(body["as_of"])
    assert abs((datetime.now(UTC) - returned).total_seconds()) < 60  # ≈ now


@pytest.mark.asyncio
@pytest.mark.parametrize("uer", [False, True])
async def test_as_of_pins_window_excludes_newer_fetch(aclient, db_session, monkeypatch, uer):
    """The core stability fix, on BOTH paths: a row fetched AFTER the cursor is excluded."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", uer)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    t0 = datetime.now(UTC) - timedelta(days=3)
    await _article_at(db_session, src, published=t0, fetched=t0, title="Old")
    cursor = t0 + timedelta(hours=1)
    later = t0 + timedelta(days=2)
    await _article_at(db_session, src, published=later, fetched=later, title="NewerFetch")
    await db_session.flush()

    body = (await aclient.get("/feed", params={"per_page": 50, "as_of": cursor.isoformat()})).json()
    titles = [it["title"] for it in body["articles"]]
    assert "Old" in titles
    assert "NewerFetch" not in titles          # fetched after the cursor → pinned out
    # a valid cursor is echoed (same instant; server serializes UTC as "…Z", client sent "+00:00")
    assert datetime.fromisoformat(body["as_of"]) == cursor


@pytest.mark.asyncio
async def test_omitting_as_of_is_unfiltered_legacy(aclient, db_session, monkeypatch):
    """Regression: no as_of → NO fetched_at filter → byte-identical legacy behavior (all rows)."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", False)
    src = await _src(db_session)
    now = datetime.now(UTC)
    await _article_at(db_session, src, published=now, fetched=now, title="Fresh")
    await _article_at(db_session, src, published=now - timedelta(days=1), fetched=now, title="Older")
    await db_session.flush()

    body = (await aclient.get("/feed?per_page=50")).json()
    assert {it["title"] for it in body["articles"]} == {"Fresh", "Older"}
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_same_cursor_stable_across_new_ingest(aclient, db_session, monkeypatch):
    """Page 1 (no cursor) pins as_of; a BREAKING story ingested before page 2 must NOT appear on
    page 2 nor duplicate/drop any page-1 row (personalized path)."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    now = datetime.now(UTC)
    for i in range(6):
        t = now - timedelta(hours=6 - i)  # A0 oldest … A5 newest, all in the past
        await _article_at(db_session, src, published=t, fetched=t, title=f"A{i}")
    await db_session.flush()

    p1 = (await aclient.get("/feed?per_page=3&page=1")).json()
    cursor = p1["as_of"]
    page1_ids = [it["id"] for it in p1["articles"]]
    assert len(page1_ids) == 3

    # New ingest lands AFTER the pinned cursor.
    cursor_dt = datetime.fromisoformat(cursor)
    await _article_at(db_session, src, published=now + timedelta(hours=1),
                      fetched=cursor_dt + timedelta(seconds=1), title="BREAKING")
    await db_session.flush()

    p2 = (await aclient.get("/feed", params={"per_page": 3, "page": 2, "as_of": cursor})).json()
    page2_titles = [it["title"] for it in p2["articles"]]
    page2_ids = [it["id"] for it in p2["articles"]]
    assert "BREAKING" not in page2_titles                 # pinned out by the cursor
    assert set(page1_ids).isdisjoint(page2_ids)           # no duplicate across the boundary
    assert len(set(page1_ids) | set(page2_ids)) == 6      # all 6 originals covered, none dropped


@pytest.mark.asyncio
async def test_stale_cursor_recovers_with_fresh_cursor(aclient, db_session, monkeypatch):
    """A cursor whose window is empty (predates all data) → items=[] + a FRESH cursor to restart."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", False)
    src = await _src(db_session)
    now = datetime.now(UTC)
    await _article_at(db_session, src, published=now, fetched=now, title="Only")
    await db_session.flush()

    stale = datetime(2000, 1, 1, tzinfo=UTC)
    body = (await aclient.get("/feed", params={"as_of": stale.isoformat()})).json()
    assert body["articles"] == []
    fresh = datetime.fromisoformat(body["as_of"])
    assert fresh > stale
    assert abs((now - fresh).total_seconds()) < 60       # server issued a fresh ≈now cursor

    # Recovery: the fresh cursor returns the live article.
    body2 = (await aclient.get("/feed", params={"as_of": body["as_of"]})).json()
    assert [it["title"] for it in body2["articles"]] == ["Only"]
