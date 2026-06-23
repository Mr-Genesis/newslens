"""Unit test for the summary staleness window (E0 fix: no crash before 4am)."""
from datetime import datetime, timezone, timedelta

from app.services import summarizer


def test_staleness_cutoff_pre_4am_does_not_raise():
    # The original bug: datetime.now().replace(hour=hour-4) -> ValueError when hour < 4.
    now = datetime(2026, 6, 23, 2, 0, tzinfo=timezone.utc)
    cutoff = summarizer._staleness_cutoff(now)
    assert cutoff == now - timedelta(hours=4)


def test_staleness_cutoff_defaults_to_now():
    cutoff = summarizer._staleness_cutoff()
    assert isinstance(cutoff, datetime)
    assert cutoff < datetime.now(timezone.utc)
