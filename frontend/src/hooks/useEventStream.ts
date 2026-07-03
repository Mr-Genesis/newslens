"use client";

import { useEffect } from "react";

/** #102 — subscribe to the backend SSE signal channel (GET /events). Calls `onEvent(type, data)` for
 *  each event; closes on unmount; degrades silently when SSE is unavailable (SSR, no EventSource, or a
 *  connection error — the browser auto-reconnects). The channel carries only ids/counts, so a consumer
 *  reacts by re-fetching the normal authenticated endpoints. */
const EVENT_TYPES = ["feed_refresh", "new_cluster"] as const;

export function useEventStream(onEvent: (type: string, data: Record<string, unknown>) => void): void {
  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") return;
    const base = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";
    let es: EventSource | null = null;
    try {
      es = new EventSource(`${base}/events`);
    } catch {
      return; // degrade silently
    }
    const handlers = EVENT_TYPES.map((type) => {
      const cb = (e: MessageEvent) => {
        let data: Record<string, unknown> = {};
        try {
          data = JSON.parse(e.data);
        } catch {
          /* ignore malformed frame */
        }
        onEvent(type, data);
      };
      es!.addEventListener(type, cb as EventListener);
      return { type, cb };
    });
    es.onerror = () => {
      /* silent — EventSource reconnects on its own */
    };
    return () => {
      for (const { type, cb } of handlers) es?.removeEventListener(type, cb as EventListener);
      es?.close();
    };
  }, [onEvent]);
}
