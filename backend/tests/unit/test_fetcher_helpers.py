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
