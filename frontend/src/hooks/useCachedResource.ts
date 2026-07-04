"use client";

/**
 * useCachedResource — the ONE React binding over the two-tier cache (src/lib/cache.ts). Paints the
 * last-known value instantly, then revalidates in the background (stale-while-revalidate).
 *
 *   mount ─▶ seed from memory (sync) ─▶ [cold? load from IDB] ─▶ revalidate ─▶ swap in fresh
 *   focus ─▶ revalidate again (WebView resume)
 *
 * Never blanks the screen when a cached value exists: a failed revalidate keeps the stale data and
 * only surfaces `error` when there's nothing cached to show.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { peek, load, revalidate } from "@/lib/cache";

export type CacheStatus = "loading" | "stale" | "fresh" | "error";

interface Snapshot<T> {
  data: T | null;
  status: CacheStatus;
}

export interface CachedResource<T> {
  data: T | null;
  status: CacheStatus;
  /** a background revalidation is in flight (cached data may still be on screen). */
  validating: boolean;
  /** force a revalidation now (e.g. pull-to-refresh). */
  refresh: () => Promise<void>;
}

export function useCachedResource<T>(
  key: string | null, // null disables the hook (invalid id / not ready)
  fetcher: () => Promise<T>,
  opts: { maxAgeMs?: number; revalidateOnFocus?: boolean } = {}
): CachedResource<T> {
  const { maxAgeMs, revalidateOnFocus = true } = opts;

  // Synchronous seed from the in-memory tier — the instant-paint path.
  const seed = useCallback((): Snapshot<T> => {
    if (!key) return { data: null, status: "loading" };
    const cached = peek<T>(key, maxAgeMs);
    return { data: cached ?? null, status: cached !== undefined ? "stale" : "loading" };
  }, [key, maxAgeMs]);

  const [snap, setSnap] = useState<Snapshot<T>>(seed);
  const [validating, setValidating] = useState(false);
  const [trackedKey, setTrackedKey] = useState(key);

  // Reset synchronously when the key changes — React's "adjust state during render" pattern (not an
  // effect), so navigating between two cached stories re-seeds instantly with no loader flash.
  if (key !== trackedKey) {
    setTrackedKey(key);
    setSnap(seed());
  }

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const aliveRef = useRef(true);

  const run = useCallback(async () => {
    if (!key) return;
    // Cold start: nothing in memory but the persistent tier may hold last session's copy → paint it
    // before the network comes back.
    if (peek<T>(key, maxAgeMs) === undefined) {
      const cached = await load<T>(key, maxAgeMs);
      if (aliveRef.current && cached !== undefined) setSnap({ data: cached, status: "stale" });
    }
    setValidating(true);
    try {
      const fresh = await revalidate<T>(key, () => fetcherRef.current());
      if (aliveRef.current) setSnap({ data: fresh, status: "fresh" });
    } catch {
      if (aliveRef.current) {
        // keep cached data on screen; only show an error when we have nothing cached
        setSnap((prev) => ({
          data: prev.data,
          status: peek<T>(key, maxAgeMs) !== undefined ? "stale" : "error",
        }));
      }
    } finally {
      if (aliveRef.current) setValidating(false);
    }
  }, [key, maxAgeMs]);

  useEffect(() => {
    aliveRef.current = true;
    void run();
    return () => {
      aliveRef.current = false;
    };
  }, [run]);

  // Revalidate on foreground (tab/WebView resume) — the classic SWR refresh moment.
  useEffect(() => {
    if (!revalidateOnFocus || typeof document === "undefined") return;
    const onVisible = () => {
      if (document.visibilityState === "visible") void run();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [run, revalidateOnFocus]);

  return { data: snap.data, status: snap.status, validating, refresh: run };
}
