"""E2 integration: source upsert + admin endpoints."""
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
    r_dup = await aclient.post("/admin/sources", json={"name": "Dup", "url": "https://my.example"})
    assert r_dup.status_code == 409
    r_bad = await aclient.post("/admin/sources", json={"name": "x"})
    assert r_bad.status_code == 400
    g = await aclient.get("/admin/sources")
    assert any(s["url"] == "https://my.example" for s in g.json())
