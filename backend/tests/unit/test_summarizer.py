"""Unit tests for the no-LLM snippet fallback + the fire-and-forget summary scheduler (PR: non-blocking
+ eager summaries)."""
import pytest

from app.services.summarizer import snippet_summary


def test_snippet_summary_first_nonempty_trimmed_to_two_sentences():
    assert (
        snippet_summary(["", "First sentence. Second sentence. Third one."])
        == "First sentence. Second sentence."
    )


def test_snippet_summary_single_sentence_returned_whole():
    assert snippet_summary(["Only one sentence here"]) == "Only one sentence here"


def test_snippet_summary_all_empty_placeholder():
    assert snippet_summary(["", ""]) == "No summary available."
    assert snippet_summary([]) == "No summary available."


def test_snippet_summary_unescapes_html_entities():
    # Rows ingested before the fetcher decoded entities still carry &amp;/&#8377; in the DB.
    assert snippet_summary(["Reliance &amp; Adani"]) == "Reliance & Adani"
    assert "₹" in snippet_summary(["Price is &#8377;100 crore. More context."])


@pytest.mark.asyncio
async def test_schedule_summary_dedupes_and_runs_once(monkeypatch):
    from app.services import summarizer

    calls: list[int] = []

    async def fake_summarize(cid: int):
        calls.append(cid)

    monkeypatch.setattr(summarizer, "summarize_cluster", fake_summarize)
    summarizer._scheduled.discard(1)

    t1 = summarizer.schedule_summary(1)
    t2 = summarizer.schedule_summary(1)  # deduped while the first is still in flight
    assert t1 is not None
    assert t2 is None

    await t1
    assert calls == [1]  # ran exactly once
    assert 1 not in summarizer._scheduled  # slot cleared on completion → a later view can re-schedule


@pytest.mark.asyncio
async def test_schedule_summary_gated_off_is_noop(monkeypatch):
    from app.services import summarizer
    from app.config import settings

    monkeypatch.setattr(settings, "eager_summaries_enabled", False)
    summarizer._scheduled.discard(99)
    assert summarizer.schedule_summary(99) is None
    assert 99 not in summarizer._scheduled


@pytest.mark.asyncio
async def test_schedule_summary_holds_strong_task_ref_until_done(monkeypatch):
    # Regression (adversarial review): asyncio keeps only a WEAK ref to a bare create_task result, so
    # the task must be strongly referenced (in _tasks) until it completes — else GC could cancel the
    # background summary mid-run. The ref is cleared by the done-callback on completion.
    import asyncio

    from app.services import summarizer

    release = asyncio.Event()

    async def fake_summarize(_cid):
        await release.wait()

    monkeypatch.setattr(summarizer, "summarize_cluster", fake_summarize)
    summarizer._scheduled.discard(7)

    t = summarizer.schedule_summary(7)
    assert t is not None
    assert t in summarizer._tasks  # strong ref held while the summary is in flight

    release.set()
    await t
    assert t not in summarizer._tasks  # done-callback cleaned it up
    assert 7 not in summarizer._scheduled
