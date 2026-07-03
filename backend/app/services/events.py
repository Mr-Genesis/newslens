"""#96 — a tiny in-process pub/sub for real-time signals (GET /events, SSE).

A singleton hub. Jobs `publish(type, data)`; each subscriber gets its own bounded, drop-oldest queue,
so a slow/stalled SSE client can NEVER block a fetch or clustering job. Carries only ids/counts, never
per-user data. In-process only — reaches clients on the same uvicorn worker (fine for the single-process
deploy; a multi-worker future would need a shared broker).
"""
import asyncio

import structlog

logger = structlog.get_logger()


class EventHub:
    def __init__(self, maxsize: int = 100):
        self._subscribers: set[asyncio.Queue] = set()
        self._maxsize = maxsize

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event_type: str, data: dict | None = None) -> None:
        """Fan out to every subscriber. Never blocks: a full queue drops its oldest event."""
        evt = {"type": event_type, "data": data or {}}
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()  # drop oldest
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass

    async def subscribe(self):
        """Async generator yielding events for one subscriber; auto-unregisters on close/disconnect."""
        q = self.register()
        try:
            while True:
                yield await q.get()
        finally:
            self.unregister(q)


hub = EventHub()


def publish(event_type: str, data: dict | None = None) -> None:
    """Module-level convenience over the singleton hub (what the scheduler jobs call)."""
    hub.publish(event_type, data)
