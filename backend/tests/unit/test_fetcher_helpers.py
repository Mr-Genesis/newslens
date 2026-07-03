"""Phase 1 fetcher fixes: per-source volume cap + full-text-over-summary body selection."""
from types import SimpleNamespace

from app.services.fetcher import _best_body, _capped_entries


def test_capped_entries_limits_when_cap_set():
    entries = list(range(10))
    assert _capped_entries(entries, 3) == [0, 1, 2]  # newest-first, first N


def test_capped_entries_passthrough_when_no_cap():
    entries = list(range(10))
    assert _capped_entries(entries, None) == entries


def test_best_body_prefers_longer_content_over_short_summary():
    # Substack ships a short `summary` AND the full `content:encoded` — take the longer one,
    # so full text is not discarded exactly when it's available.
    entry = SimpleNamespace(
        summary="Short teaser.",
        content=[{"value": "The full article body, which is considerably longer than the teaser."}],
    )
    assert "full article body" in _best_body(entry)


def test_best_body_uses_summary_when_no_content():
    entry = SimpleNamespace(summary="Only a summary here.")
    assert _best_body(entry) == "Only a summary here."


def test_best_body_empty_when_neither():
    assert _best_body(SimpleNamespace()) == ""


# ── official-sources Phase 1 hygiene ──
from app.services.fetcher import _fetch_timeout, _is_probably_english, _normalize_link  # noqa: E402


def test_normalize_link_fixes_sebi_double_prefix():
    # SEBI's feed emits https://www.sebi.gov.in/https://www.sebi.gov.in/...pdf
    bad = "https://www.sebi.gov.in/https://www.sebi.gov.in/enforcement/orders/jul-2026/order.pdf"
    assert _normalize_link(bad) == "https://www.sebi.gov.in/enforcement/orders/jul-2026/order.pdf"


def test_normalize_link_leaves_good_urls_alone():
    good = "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12898"
    assert _normalize_link(good) == good
    # a URL legitimately containing http in a query param must survive
    q = "https://ex.example/redirect?url=https%3A%2F%2Fother.example"
    assert _normalize_link(q) == q


def test_is_probably_english():
    assert _is_probably_english("RBI issues Master Direction on digital lending") is True
    # Devanagari (the PIB Hindi failure mode)
    assert _is_probably_english("प्रधानमंत्री ने उद्घाटन किया") is False


def test_fetch_timeout_honors_slow_source_meta():
    fast = SimpleNamespace(credibility_meta=None)
    slow = SimpleNamespace(credibility_meta={"fetch_timeout": 45})  # NITI needs >20s
    assert _fetch_timeout(fast) == 30.0
    assert _fetch_timeout(slow) == 45.0
