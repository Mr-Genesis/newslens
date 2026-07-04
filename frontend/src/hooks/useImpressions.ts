"use client";

/**
 * WS-1 (#111): impression logging — the ONE shared hook every surface uses (briefing / feed /
 * rail / discover). Never copy this logic into a component.
 *
 * A card counts as "seen" when ≥50% visible for ≥1s (IntersectionObserver + dwell timer).
 * Seen ids buffer client-side (session-deduped, cap 200 drop-oldest) and flush every 5s and on
 * pagehide/unmount. Fire-and-forget: the server dedupes per day and caps volume; a failed flush
 * re-buffers once so a cold backend doesn't lose the batch.
 */
import { useCallback, useEffect, useRef } from "react";

import { postImpressions, type ImpressionItem } from "@/lib/api";

const VISIBILITY_MS = 1000;
const FLUSH_INTERVAL_MS = 5000;
const BUFFER_CAP = 200;

type Surface = ImpressionItem["surface"];

export function useImpressions(surface: Surface) {
  const buffer = useRef<ImpressionItem[]>([]);
  const seen = useRef<Set<string>>(new Set()); // session-level dedupe (server dedupes per day)
  const timers = useRef<Map<Element, ReturnType<typeof setTimeout>>>(new Map());
  const observer = useRef<IntersectionObserver | null>(null);
  const retried = useRef(false);

  const enqueue = useCallback(
    (item: ImpressionItem) => {
      const key = `${item.cluster_id ?? ""}:${item.article_id ?? ""}:${surface}`;
      if (seen.current.has(key)) return;
      seen.current.add(key);
      buffer.current.push(item);
      if (buffer.current.length > BUFFER_CAP) buffer.current.shift(); // drop-oldest
    },
    [surface]
  );

  const flush = useCallback(async () => {
    if (buffer.current.length === 0) return;
    const items = buffer.current.splice(0, buffer.current.length);
    try {
      await postImpressions(items);
      retried.current = false;
    } catch {
      // one re-buffer so a sleeping backend doesn't eat the batch; second failure drops it
      if (!retried.current) {
        retried.current = true;
        buffer.current.unshift(...items.slice(0, BUFFER_CAP));
      }
    }
  }, []);

  useEffect(() => {
    // The flush machinery (interval + pagehide) must run even where IntersectionObserver doesn't
    // exist (jsdom, ancient WebViews) — logNow-only surfaces (discover) still need their buffer
    // flushed. Only the OBSERVER is conditional.
    if (typeof IntersectionObserver !== "undefined") {
      observer.current = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            const el = entry.target as HTMLElement;
            if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
              if (!timers.current.has(el)) {
                timers.current.set(
                  el,
                  setTimeout(() => {
                    const clusterId = el.dataset.impressionCluster;
                    const articleId = el.dataset.impressionArticle;
                    if (clusterId || articleId) {
                      enqueue({
                        cluster_id: clusterId ? Number(clusterId) : null,
                        article_id: articleId ? Number(articleId) : null,
                        surface,
                      });
                    }
                  }, VISIBILITY_MS)
                );
              }
            } else {
              const t = timers.current.get(el);
              if (t) {
                clearTimeout(t);
                timers.current.delete(el);
              }
            }
          }
        },
        { threshold: 0.5 }
      );
    }

    const interval = setInterval(flush, FLUSH_INTERVAL_MS);
    const onHide = () => void flush();
    window.addEventListener("pagehide", onHide);
    document.addEventListener("visibilitychange", onHide);

    return () => {
      clearInterval(interval);
      window.removeEventListener("pagehide", onHide);
      document.removeEventListener("visibilitychange", onHide);
      for (const t of timers.current.values()) clearTimeout(t);
      timers.current.clear();
      observer.current?.disconnect();
      void flush(); // unmount flush
    };
  }, [surface, enqueue, flush]);

  /** Ref callback: attach to a card wrapper carrying data-impression-cluster / -article. */
  const observe = useCallback((el: HTMLElement | null) => {
    if (el && observer.current) observer.current.observe(el);
  }, []);

  /** Manual log for non-scroll surfaces (discover shows one card at a time). */
  const logNow = useCallback(
    (ids: { clusterId?: number | null; articleId?: number | null }) => {
      if (ids.clusterId == null && ids.articleId == null) return;
      enqueue({
        cluster_id: ids.clusterId ?? null,
        article_id: ids.articleId ?? null,
        surface,
      });
    },
    [enqueue, surface]
  );

  return { observe, logNow, flush };
}
