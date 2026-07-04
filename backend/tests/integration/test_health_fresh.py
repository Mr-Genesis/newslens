"""WS-8 (#118): GET /health/fresh — the freshness alarm. 503 when the newest article was fetched
beyond the threshold (an external pinger emails on non-200)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Article, Source, SourceType

UTC = timezone.utc
_n = 0


async def _article(db, fetched):
    global _n
    _n += 1
    src = Source(name=f"S{_n}", url=f"https://h/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    db.add(Article(title="T", url=f"https://h/{_n}/a", source_id=src.id, fetched_at=fetched))
    await db.flush()


@pytest.mark.asyncio
async def test_health_fresh_ok_when_recent(aclient, db_session):
    await _article(db_session, datetime.now(UTC))
    r = await aclient.get("/health/fresh")
    assert r.status_code == 200
    body = r.json()
    assert body["fresh"] is True
    assert body["age_minutes"] is not None and body["threshold_minutes"] == 45


@pytest.mark.asyncio
async def test_health_fresh_503_when_stale(aclient, db_session):
    await _article(db_session, datetime.now(UTC) - timedelta(minutes=90))  # past the 45-min alarm
    r = await aclient.get("/health/fresh")
    assert r.status_code == 503
    assert r.json()["fresh"] is False


@pytest.mark.asyncio
async def test_health_fresh_503_when_no_articles(aclient, db_session):
    r = await aclient.get("/health/fresh")
    assert r.status_code == 503
    assert r.json()["latest_article_fetched_at"] is None


@pytest.mark.asyncio
async def test_health_fresh_threshold_boundary(aclient, db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "freshness_alarm_minutes", 30)
    await _article(db_session, datetime.now(UTC) - timedelta(minutes=20))  # inside a 30-min window
    r = await aclient.get("/health/fresh")
    assert r.status_code == 200 and r.json()["fresh"] is True
