"""Phase 3 — the NSE per-company filing feeds are seeded correctly (watchlist-only, name-matched).

These 4 are the live feeds re-verified 2026-07-04 (the combined NSE/BSE "Corporate Announcements"
firehoses 404'd / are walled and must NOT be seeded). Each is a `filing` source with audience=[]
(invisible except via a watchlist/follow) and the `filing_watchlist` meta the ingest filter keys on.
"""
from app.services.fetcher import load_feeds

FILING_LANDMARKS = {
    "NSE Board Meetings",
    "NSE Financial Results",
    "NSE Insider Trading",
    "NSE Voting Results",
}


def test_nse_filing_feeds_are_seeded_watchlist_only():
    by_name = {f["name"]: f for f in load_feeds()}
    assert FILING_LANDMARKS <= set(by_name), f"missing: {FILING_LANDMARKS - set(by_name)}"
    for name in FILING_LANDMARKS:
        f = by_name[name]
        assert f["source_type"] == "filing"
        # audience=[] ⇒ the source-gate hides it; only the watchlist/follow read-path reveals it.
        assert f.get("audience") == [], f"{name} must be watchlist-only (audience=[])"
        meta = f.get("credibility_meta") or {}
        assert meta.get("filing_watchlist") is True, f"{name} needs filing_watchlist=true"
        assert meta.get("filing_parser") == "nse_name", f"{name} needs the nse_name parser"
        # nsearchives host is the one that serves plain curl (www.nseindia.com is Akamai-walled).
        assert "nsearchives.nseindia.com" in f["rss_url"]
        assert isinstance(f.get("credibility_score"), int) and 0 <= f["credibility_score"] <= 100


def test_dead_and_walled_exchange_feeds_are_not_seeded():
    """The combined Corporate-Announcements firehoses are dead (NSE 404) / walled (BSE JSON API) —
    seeding them would silently ingest an HTML error page or nothing."""
    rss = " ".join((f.get("rss_url") or "").lower() for f in load_feeds())
    assert "corporate_announcements" not in rss
    assert "corpannouncement" not in rss  # BSE /data/xml/corpannouncement.xml (404 ASP.NET error page)
