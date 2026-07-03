"""Phase 3 — India exchange filings: entity attach, aggregate watch keys, ingest, read-path.

Real Postgres (see conftest). The filing tier is watchlist-only: a filing is ingested only when
some user watchlists its company, attaches deterministically to that company's org entity, and is
visible in the feed ONLY to a user whose own watchlist/follows resolve to that entity.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import (
    Article,
    ArticleEntity,
    Entity,
    EntityAlias,
    Follow,
    Source,
    SourceType,
    User,
)
from app.services import entities, filings


async def _filing_source(db, name="NSE Financial Results"):
    src = Source(
        name=name, url=f"https://ex.example/{name}", rss_url=f"https://ex.example/{name}/rss",
        source_type=SourceType.filing, region="in", category="finance",
        audience=[], credibility_score=90,
        credibility_meta={"filing_watchlist": True, "filing_parser": "nse_name"},
    )
    db.add(src)
    await db.flush()
    return src


async def _article(db, src, title):
    a = Article(title=title, url=f"https://ex.example/a/{title}", source_id=src.id,
                published_at=datetime.now(timezone.utc))
    db.add(a)
    await db.flush()
    return a


@pytest.mark.asyncio
async def test_attach_filing_entity_creates_org_and_norm_alias(db_session):
    src = await _filing_source(db_session)
    art = await _article(db_session, src, "Reliance Industries Limited")

    await filings.attach_filing_entity(db_session, art, "Reliance Industries Limited")

    ent = (await db_session.execute(
        select(Entity).where(Entity.name_norm == "reliance industries limited")
    )).scalar_one()
    assert ent.kind == "org"
    # The norm_company key is stored as an alias so the read-path resolves a watchlist value to it.
    aliases = (await db_session.execute(
        select(EntityAlias.alias_norm).where(EntityAlias.entity_id == ent.id)
    )).scalars().all()
    assert "reliance industries" in aliases
    link = (await db_session.execute(
        select(ArticleEntity).where(ArticleEntity.article_id == art.id,
                                    ArticleEntity.entity_id == ent.id)
    )).scalar_one()
    assert link.salience == 1.0  # deterministic attach — full confidence, no LLM


@pytest.mark.asyncio
async def test_attach_filing_entity_is_idempotent(db_session):
    src = await _filing_source(db_session)
    art = await _article(db_session, src, "Infosys Limited")
    await filings.attach_filing_entity(db_session, art, "Infosys Limited")
    await filings.attach_filing_entity(db_session, art, "Infosys Limited")  # re-ingest / re-run

    assert (await db_session.execute(
        select(func.count()).select_from(Entity).where(Entity.name_norm == "infosys limited")
    )).scalar_one() == 1
    assert (await db_session.execute(
        select(func.count()).select_from(ArticleEntity).where(ArticleEntity.article_id == art.id)
    )).scalar_one() == 1


@pytest.mark.asyncio
async def test_attached_entity_resolves_from_watchlist_value(db_session):
    """Closes the loop: after attach, a user's watchlist value resolves to the same entity, so the
    read-path (resolve_existing) and the ingest key agree."""
    src = await _filing_source(db_session)
    art = await _article(db_session, src, "Reliance Industries Limited")
    await filings.attach_filing_entity(db_session, art, "Reliance Industries Limited")

    # Full legal name → name_norm; the shorter watchlisted form → the norm alias. Both resolve.
    assert await entities.resolve_existing(db_session, "Reliance Industries Limited") is not None
    assert await entities.resolve_existing(db_session, "Reliance Industries") is not None


@pytest.mark.asyncio
async def test_attach_reuses_existing_org_entity(db_session):
    """A filing must not duplicate a company entity that news extraction already created."""
    existing = Entity(canonical_name="Tata Motors Limited", name_norm="tata motors limited", kind="org")
    db_session.add(existing)
    await db_session.flush()
    src = await _filing_source(db_session)
    art = await _article(db_session, src, "Tata Motors Limited")

    await filings.attach_filing_entity(db_session, art, "Tata Motors Limited")

    assert (await db_session.execute(
        select(func.count()).select_from(Entity).where(Entity.name_norm == "tata motors limited")
    )).scalar_one() == 1
    link = (await db_session.execute(
        select(ArticleEntity).where(ArticleEntity.article_id == art.id)
    )).scalar_one()
    assert link.entity_id == existing.id


# ── aggregate_watch_keys: the union of company keys the global ingest filter admits ──
@pytest.mark.asyncio
async def test_aggregate_watch_keys_unions_all_users(db_session):
    db_session.add(User(id=201, watchlist=[{"type": "ticker", "value": "Reliance Industries"}]))
    db_session.add(User(id=202, watchlist=[{"type": "entity", "value": "Infosys Ltd"},
                                           {"type": "region", "value": "US-CA"}]))
    db_session.add(User(id=203, watchlist=[]))
    await db_session.flush()
    db_session.add(Follow(user_id=203, kind="entity", value="Tata Motors Limited"))
    await db_session.flush()

    keys = await filings.aggregate_watch_keys(db_session)
    assert {"reliance industries", "infosys", "tata motors"} <= keys
    # region/topic watchlist entries are NOT companies — their normalized value must not become a key.
    assert "us ca" not in keys


@pytest.mark.asyncio
async def test_aggregate_watch_keys_empty_when_nobody_watchlists(db_session):
    db_session.add(User(id=210, watchlist=[]))
    db_session.add(User(id=211, watchlist=None))
    await db_session.flush()
    assert await filings.aggregate_watch_keys(db_session) == set()


# ── ingest filter + attach: the firehose is reduced to watchlisted companies, and attached ──
class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.headers = {"content-type": "application/rss+xml"}

    def raise_for_status(self):
        pass


class _FakeClient:
    def __init__(self, body):
        self._body = body
        self.calls = []

    async def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        return _FakeResp(self._body)


# NSE per-company shape: full legal name in <title>, XBRL <link>, IST <pubDate> (no tz), no symbol.
_NSE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>NSE News - Latest Financial Results</title>
<item><title>Reliance Industries Limited</title>
<link>https://nsearchives.nseindia.com/corporate/xbrl/FR_1_WEB.xml</link>
<description>TYPE OF SECURITY : Equity Shares</description><pubDate>03-Jul-2026 19:49:34</pubDate></item>
<item><title>Tata Motors Limited</title>
<link>https://nsearchives.nseindia.com/corporate/xbrl/FR_2_WEB.xml</link>
<description>TYPE OF SECURITY : Equity Shares</description><pubDate>03-Jul-2026 18:10:00</pubDate></item>
</channel></rss>"""


async def _nse_filing_src(db):
    src = Source(name="NSE Financial Results", url="https://nsearchives.nseindia.com/fr",
                 rss_url="https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml",
                 source_type=SourceType.filing, region="in", category="finance",
                 audience=[], credibility_score=90, per_fetch_cap=40,
                 credibility_meta={"filing_watchlist": True, "filing_parser": "nse_name"})
    db.add(src)
    await db.flush()
    return src


@pytest.mark.asyncio
async def test_ingest_keeps_only_watchlisted_company_and_attaches(db_session):
    from app.services import fetcher

    # Someone watchlists Reliance (by name) — Tata is watchlisted by nobody.
    db_session.add(User(id=301, watchlist=[{"type": "ticker", "value": "Reliance Industries"}]))
    src = await _nse_filing_src(db_session)
    await db_session.flush()

    n = await fetcher.fetch_single_feed(src, _FakeClient(_NSE_RSS), session=db_session)

    assert n == 1  # Tata dropped — the firehose is reduced to watchlisted companies
    arts = (await db_session.execute(
        select(Article).where(Article.source_id == src.id))).scalars().all()
    assert {a.title for a in arts} == {"Reliance Industries Limited"}
    # …and the kept filing is attached to its org entity (cast strip works with no LLM).
    ent = (await db_session.execute(
        select(Entity).where(Entity.name_norm == "reliance industries limited"))).scalar_one()
    assert (await db_session.execute(
        select(ArticleEntity).where(ArticleEntity.article_id == arts[0].id,
                                    ArticleEntity.entity_id == ent.id))).scalar_one() is not None


@pytest.mark.asyncio
async def test_ingest_drops_everything_when_nobody_watchlists(db_session):
    """The corpus-protection invariant: an empty aggregate watchlist ingests NOTHING from a firehose
    — a filing source never dumps thousands of unwanted disclosures."""
    from app.services import fetcher

    src = await _nse_filing_src(db_session)
    await db_session.flush()
    n = await fetcher.fetch_single_feed(src, _FakeClient(_NSE_RSS), session=db_session)
    assert n == 0
    assert (await db_session.execute(
        select(func.count()).select_from(Article).where(Article.source_id == src.id))).scalar_one() == 0


# ── feed read-path: a filing is visible ONLY to a user whose own watchlist/follows resolve to it ──
async def _feed_titles(aclient, **params):
    r = await aclient.get("/feed", params=params)
    assert r.status_code == 200
    return {a["title"] for a in r.json()["articles"]}


async def _seed_reliance_filing(db):
    src = await _filing_source(db, name="NSE Board Meetings")
    art = await _article(db, src, "Reliance Industries Limited")
    await filings.attach_filing_entity(db, art, "Reliance Industries Limited")
    await db.flush()
    return src, art


@pytest.mark.asyncio
async def test_filing_visible_only_when_watchlisted(aclient, db_session):
    await _seed_reliance_filing(db_session)

    # No watchlist → the filing is hidden (audience=[] fails the source-gate; nothing to widen it).
    assert "Reliance Industries Limited" not in await _feed_titles(aclient)

    # Watchlist the company by name → the read-path resolves it to the entity → it appears.
    await aclient.put("/profile", json={"watchlist": [{"type": "ticker", "value": "Reliance Industries"}]})
    assert "Reliance Industries Limited" in await _feed_titles(aclient)


@pytest.mark.asyncio
async def test_filing_not_leaked_by_unrelated_watchlist(aclient, db_session):
    """Per-user isolation: watchlisting a DIFFERENT company must not surface another company's filing
    (the read-path scopes to the caller's own entities, not the aggregate that gated ingestion)."""
    await _seed_reliance_filing(db_session)
    await aclient.put("/profile", json={"watchlist": [{"type": "ticker", "value": "Infosys"}]})
    assert "Reliance Industries Limited" not in await _feed_titles(aclient)


@pytest.mark.asyncio
async def test_filing_chip_shows_watchlisted_filings(aclient, db_session):
    """?source_type=filing composes with the widening: it shows the user's watchlisted filings, not
    an empty list and not other users' companies."""
    await _seed_reliance_filing(db_session)
    await aclient.put("/profile", json={"watchlist": [{"type": "ticker", "value": "Reliance Industries"}]})
    assert "Reliance Industries Limited" in await _feed_titles(aclient, source_type="filing")


# ── dark-launch: exchange_filings_enabled=false ⇒ no ingest, no visibility (byte-identical) ──
@pytest.mark.asyncio
async def test_dark_launch_off_ingests_nothing_even_when_watchlisted(db_session, monkeypatch):
    from app.config import settings as cfg
    from app.services import fetcher

    monkeypatch.setattr(cfg, "exchange_filings_enabled", False)
    db_session.add(User(id=401, watchlist=[{"type": "ticker", "value": "Reliance Industries"}]))
    src = await _nse_filing_src(db_session)
    await db_session.flush()
    assert await fetcher.fetch_single_feed(src, _FakeClient(_NSE_RSS), session=db_session) == 0


@pytest.mark.asyncio
async def test_dark_launch_off_hides_watchlisted_filing(aclient, db_session, monkeypatch):
    from app.config import settings as cfg

    await _seed_reliance_filing(db_session)
    await aclient.put("/profile", json={"watchlist": [{"type": "ticker", "value": "Reliance Industries"}]})
    assert "Reliance Industries Limited" in await _feed_titles(aclient)  # on by default

    monkeypatch.setattr(cfg, "exchange_filings_enabled", False)
    assert "Reliance Industries Limited" not in await _feed_titles(aclient)  # kill-switch hides it


# ── the source-follow escape hatch must NOT bypass per-company filing scoping (review fix) ──
@pytest.mark.asyncio
async def test_source_follow_does_not_leak_filings(aclient, db_session):
    """A filing source is one exchange firehose of thousands of companies. Following it must NOT
    flood a user with every watchlisted company's filings — the #81 follow-source escape hatch
    (which bypasses floor+audience) has to exclude filing sources, or per-user isolation is defeated."""
    src, _ = await _seed_reliance_filing(db_session)
    await aclient.put("/profile", json={"profession": "poet"})  # user 1, NO watchlist
    # Even a source-follow that already exists on the account must not admit the firehose.
    db_session.add(Follow(user_id=1, kind="source", value=str(src.id)))
    await db_session.flush()
    assert "Reliance Industries Limited" not in await _feed_titles(aclient)


@pytest.mark.asyncio
async def test_cannot_follow_a_filing_source(aclient, db_session):
    """And the misleading follow can't be created in the first place — watchlist the company instead."""
    src, _ = await _seed_reliance_filing(db_session)
    r = await aclient.post("/follows", json={"kind": "source", "value": str(src.id)})
    assert r.status_code == 400
