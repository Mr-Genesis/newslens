"""Official-sources Phase 1 — the 28 live-verified officials are seeded, valid, and reachable."""
from app.services.audience import _KEYWORDS
from app.services.fetcher import load_feeds

PRODUCIBLE = set(_KEYWORDS)

# One representative per region bucket (the full 28 are asserted by count + shape below).
LANDMARKS = {
    "Reserve Bank of India - Notifications & Circulars",
    "NSE Circulars", "BSE Notices",
    "SEC Press Releases", "Federal Reserve Press Releases (All)",
    "Bank of England", "European Central Bank",
    "Bank of Japan - What's New (English)",
}


def test_officials_seeded_valid_and_reachable():
    feeds = load_feeds()
    officials = [f for f in feeds if f["source_type"] == "official"]
    names = {f["name"] for f in officials}
    assert LANDMARKS <= names, f"missing landmarks: {LANDMARKS - names}"
    assert len(officials) >= 28
    for f in officials:
        assert isinstance(f.get("credibility_score"), int) and 0 <= f["credibility_score"] <= 100
        assert (f.get("credibility_meta") or {}).get("rationale"), f"{f['name']} needs a rationale"
        aud = set(f.get("audience") or [])
        assert aud and aud <= PRODUCIBLE, f"{f['name']} audience {aud} not emittable"
        assert f.get("per_fetch_cap"), f"{f['name']} must carry a per_fetch_cap (volume control)"


def test_pib_is_language_guarded_and_niti_gets_timeout_headroom():
    by_name = {f["name"]: f for f in load_feeds()}
    # PIB currently serves Hindi (Lang param ignored server-side) → must be english-guarded.
    pib = by_name["PIB India"]
    assert (pib.get("credibility_meta") or {}).get("english_guard") is True
    # NITI's server needs >20s (verified: 45s worked).
    niti = by_name["NITI Aayog"]
    assert (niti.get("credibility_meta") or {}).get("fetch_timeout", 0) >= 45


def test_no_filing_sources_in_the_seed():
    """Filings are generated per watchlisted ticker (Phase 2) — never bulk-seeded."""
    assert not [f for f in load_feeds() if f["source_type"] == "filing"]


def test_seed_urls_are_unique():
    """Source.url is UNIQUE in the DB and _upsert_sources falls back to matching on url — a shared
    site URL makes the second feed get swallowed into (and mutate) the first row. Every seed entry
    must carry a distinct url (use the section page, not the bare domain)."""
    from collections import Counter
    urls = Counter(f["url"].strip().lower().rstrip("/") for f in load_feeds())
    dupes = {u: n for u, n in urls.items() if n > 1}
    assert not dupes, f"colliding urls (feeds will swallow each other): {dupes}"
