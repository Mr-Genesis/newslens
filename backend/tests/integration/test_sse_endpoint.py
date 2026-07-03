"""#101 — GET /events SSE endpoint streaming from the in-process hub (unauthenticated signal channel)."""
import asyncio
import json

import pytest


@pytest.mark.asyncio
async def test_sse_stream_yields_a_published_event():
    from app.api.routes import _sse_stream
    from app.services import events

    agen = _sse_stream()
    task = asyncio.ensure_future(agen.__anext__())
    await asyncio.sleep(0)  # let the subscription register
    events.publish("feed_refresh", {"new_articles": 7})
    frame = await asyncio.wait_for(task, timeout=1)
    assert frame["event"] == "feed_refresh" and json.loads(frame["data"])["new_articles"] == 7
    await agen.aclose()


@pytest.mark.asyncio
async def test_events_endpoint_returns_an_event_source_response():
    # Call the handler directly (streaming it over the in-process test transport would hang, since
    # ASGITransport doesn't deliver the client-disconnect that ends the infinite stream).
    from sse_starlette.sse import EventSourceResponse

    from app.api.routes import sse_events
    resp = await sse_events()
    assert isinstance(resp, EventSourceResponse)
    assert resp.media_type == "text/event-stream"
