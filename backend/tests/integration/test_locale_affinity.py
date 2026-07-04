"""WS-7 (#117): locale region-affinity — a bounded ×[1.0, boost] nudge when a source's region matches
the user's locale, applied ONLY after an explicit profile save (persona_version > 1). Off by gate or
kill-switch → byte-identical (strict no-op)."""
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.models import Article, EmbeddingStatus, Source, SourceType, User
from app.services import ranking

UTC = timezone.utc
_n = 0


def test_locale_mult_matches_case_insensitively_and_is_bounded():
    assert ranking.locale_mult("in", "IN") == settings.locale_affinity_boost   # case-insensitive match
    assert ranking.locale_mult("global", "IN") == 1.0                           # region mismatch
    assert ranking.locale_mult("in", None) == 1.0                               # disabled (no locale)
    assert ranking.locale_mult(None, "IN") == 1.0                               # no source region
    assert 1.0 <= ranking.locale_mult("in", "IN") <= 1.1


async def _src(db, region):
    global _n
    _n += 1
    s = Source(name=f"S{_n}", url=f"https://loc/{_n}", source_type=SourceType.wire, region=region)
    db.add(s)
    await db.flush()
    return s


async def _article(db, src, when, title):
    global _n
    _n += 1
    a = Article(title=title, url=f"https://loc/{_n}/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete, published_at=when)
    db.add(a)
    await db.flush()
    return a


async def _seed(db, *, persona_version):
    """User 1 with locale IN; an IN-region article (created FIRST → lower id) and a global-region one,
    same publish time. In a pure tie the sort's id-desc tiebreak puts the higher-id (global) first, so
    'IN first' unambiguously means the locale boost fired."""
    u = await db.get(User, 1)
    if u is None:
        u = User(id=1)
        db.add(u)
    u.locale = "IN"
    u.persona_version = persona_version
    await db.flush()
    now = datetime.now(UTC)
    await _article(db, await _src(db, "in"), now, "IN story")        # lower id
    await _article(db, await _src(db, "global"), now, "Global story")  # higher id


async def _order(aclient):
    body = (await aclient.get("/feed?per_page=50")).json()
    return [it["title"] for it in body["articles"]]


@pytest.mark.asyncio
async def test_boost_applies_after_profile_save(aclient, db_session, monkeypatch):
    monkeypatch.setattr(settings, "uer_enabled", True)
    monkeypatch.setattr(settings, "locale_affinity_enabled", True)
    await _seed(db_session, persona_version=2)  # explicit persona → boost active
    order = await _order(aclient)
    assert order.index("IN story") < order.index("Global story")  # IN lifted above the (higher-id) global


@pytest.mark.asyncio
async def test_default_persona_gets_no_boost(aclient, db_session, monkeypatch):
    monkeypatch.setattr(settings, "uer_enabled", True)
    monkeypatch.setattr(settings, "locale_affinity_enabled", True)
    await _seed(db_session, persona_version=1)  # never saved a profile → gate closed
    order = await _order(aclient)
    assert order.index("Global story") < order.index("IN story")  # no boost → id-desc tiebreak wins


@pytest.mark.asyncio
async def test_kill_switch_disables_boost(aclient, db_session, monkeypatch):
    monkeypatch.setattr(settings, "uer_enabled", True)
    monkeypatch.setattr(settings, "locale_affinity_enabled", False)
    await _seed(db_session, persona_version=2)  # persona saved, but the switch is off
    order = await _order(aclient)
    assert order.index("Global story") < order.index("IN story")  # off → byte-identical to no-boost
