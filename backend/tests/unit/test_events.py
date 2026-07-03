"""#96 — in-process event hub: fan-out, bounded drop-oldest, no-op without subscribers."""
import asyncio

import pytest

from app.services.events import EventHub


@pytest.mark.asyncio
async def test_hub_fans_out_to_every_subscriber():
    h = EventHub()
    q1, q2 = h.register(), h.register()
    h.publish("feed_refresh", {"new_articles": 3})
    e1, e2 = q1.get_nowait(), q2.get_nowait()
    assert e1["type"] == "feed_refresh" and e1["data"]["new_articles"] == 3
    assert e2 == e1
    h.unregister(q1)
    h.unregister(q2)


def test_publish_with_no_subscribers_is_noop():
    EventHub().publish("feed_refresh", {"new_articles": 1})  # must not raise


@pytest.mark.asyncio
async def test_hub_drops_oldest_on_overflow():
    h = EventHub(maxsize=2)
    q = h.register()
    for i in range(5):
        h.publish("x", {"i": i})
    got = []
    while not q.empty():
        got.append(q.get_nowait()["data"]["i"])
    assert got == [3, 4]  # a stalled consumer keeps only the newest; oldest dropped, publish never blocks


@pytest.mark.asyncio
async def test_subscribe_yields_events_published_after_subscription():
    h = EventHub()
    agen = h.subscribe()
    task = asyncio.ensure_future(agen.__anext__())
    await asyncio.sleep(0)  # let the generator register its queue
    h.publish("new_cluster", {"count": 2})
    evt = await asyncio.wait_for(task, timeout=1)
    assert evt["type"] == "new_cluster" and evt["data"]["count"] == 2
    await agen.aclose()
