"""E2 integration: source upsert + admin endpoints + GDELT region inference."""
import contextlib

import pytest
from sqlalchemy import func, select

from app.models import Source
from app.services import fetcher


@pytest.mark.asyncio
async def test_ensure_sources_upsert_idempotent_and_backfills_region(db_session):
    feeds = fetcher.load_feeds()
    f0 = feeds[0]
    # pre-existing row matching a feed by url, but missing region
    db_session.add(Source(name=f0["name"], url=f0["url"], rss_url=f0["rss_url"], region=None))
    await db_session.flush()

    await fetcher.ensure_sources(db_session)
    total = (await db_session.execute(select(func.count()).select_from(Source))).scalar()
    assert total == len(feeds)  # upserted, not duplicated

    s0 = (
        await db_session.execute(select(Source).where(Source.url == f0["url"]))
    ).scalar_one()
    assert s0.region == f0["region"]  # backfilled

    # idempotent
    await fetcher.ensure_sources(db_session)
    total2 = (await db_session.execute(select(func.count()).select_from(Source))).scalar()
    assert total2 == len(feeds)


@pytest.mark.asyncio
async def test_admin_create_source(aclient, db_session):
    r = await aclient.post(
        "/admin/sources",
        json={"name": "My Feed", "url": "https://my.example",
              "rss_url": "https://my.example/rss", "region": "in", "category": "tech"},
    )
    assert r.status_code == 200
    assert r.json()["updated"] is False
    # Re-posting the same url upserts in place (no duplicate, no 409).
    r_dup = await aclient.post("/admin/sources", json={"name": "Dup", "url": "https://my.example"})
    assert r_dup.status_code == 200
    assert r_dup.json()["updated"] is True
    r_bad = await aclient.post("/admin/sources", json={"name": "x"})
    assert r_bad.status_code == 400
    g = await aclient.get("/admin/sources")
    matches = [s for s in g.json() if s["url"] == "https://my.example"]
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_admin_post_source_creates_row(aclient, db_session):
    """POST /admin/sources with a fresh url inserts exactly one persisted source row."""
    r = await aclient.post(
        "/admin/sources",
        json={"name": "Fresh Feed", "url": "https://fresh.example",
              "rss_url": "https://fresh.example/rss", "region": "in", "category": "business"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] is False
    assert body["name"] == "Fresh Feed"

    s = (
        await db_session.execute(
            select(Source).where(Source.url == "https://fresh.example")
        )
    ).scalar_one()
    assert s.region == "in"
    assert s.category == "business"
    assert s.rss_url == "https://fresh.example/rss"


@pytest.mark.asyncio
async def test_admin_post_source_upserts_existing(aclient, db_session):
    """Re-POSTing an existing url updates region/category in place (upsert), and the
    plain /admin/sources path that detects a duplicate name returns 409 — but the
    canonical upsert (same url, new metadata) must NOT 409; it must update the row."""
    r1 = await aclient.post(
        "/admin/sources",
        json={"name": "Up Feed", "url": "https://up.example",
              "region": "global", "category": "world"},
    )
    assert r1.status_code == 200
    assert r1.json()["updated"] is False
    first_id = r1.json()["id"]

    # Same url, new region + category -> upsert (update in place), not a duplicate insert.
    r2 = await aclient.post(
        "/admin/sources",
        json={"name": "Up Feed Renamed", "url": "https://up.example",
              "region": "in", "category": "tech"},
    )
    assert r2.status_code == 200
    assert r2.json()["updated"] is True
    assert r2.json()["id"] == first_id

    # Exactly one row, with the updated metadata.
    rows = (
        await db_session.execute(
            select(Source).where(Source.url == "https://up.example")
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].region == "in"
    assert rows[0].category == "tech"
    assert rows[0].name == "Up Feed Renamed"


@pytest.mark.asyncio
async def test_gdelt_created_source_gets_region(db_session, monkeypatch):
    """A source auto-created from GDELT discovery inherits region from the query scope:
    an India-scoped GDELT query (sourcecountry:IN) yields region 'in'."""
    from app.config import settings
    from app.services import gdelt

    # Route gdelt's own-session factory at the test transaction so the write is visible.
    @contextlib.asynccontextmanager
    async def _fake_session():
        yield db_session

    monkeypatch.setattr(gdelt, "async_session", _fake_session)
    monkeypatch.setattr(settings, "gdelt_query", "sourcecountry:IN")

    src = await gdelt._get_or_create_source(
        "thehindu.com", "https://thehindu.com/news/article"
    )
    assert src is not None
    assert src.region == "in"

    persisted = (
        await db_session.execute(
            select(Source).where(Source.url == "https://thehindu.com")
        )
    ).scalar_one()
    assert persisted.region == "in"

    # Idempotent: a second discovery for the same domain returns the existing row.
    again = await gdelt._get_or_create_source(
        "thehindu.com", "https://thehindu.com/news/other"
    )
    assert again.id == src.id
