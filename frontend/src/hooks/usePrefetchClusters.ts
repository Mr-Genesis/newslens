"use client";

/**
 * usePrefetchClusters — warm the top-N story details into the cache while the briefing/feed is on
 * screen, so tapping a card opens the deep dive INSTANTLY (DeepDiveView peeks the same cache key).
 *
 * Guards: only the first N ids (protect the already-slow backend), skips ids already cached, and
 * dedupes via revalidate() so it never double-fetches a story the user is already opening.
 */
import { useEffect } from "react";

import { getCluster } from "@/lib/api";
import { peek, revalidate, CACHE_TTL_MS } from "@/lib/cache";

export const PREFETCH_TOP_N = 3;

export function usePrefetchClusters(
  clusterIds: Array<number | null | undefined>,
  maxAgeMs: number = CACHE_TTL_MS.cluster
) {
  // Derive a stable signature (top-N numeric ids) so the effect only refires when the set changes,
  // not on every render or background revalidation that returns the same stories.
  const key = clusterIds
    .filter((x): x is number => typeof x === "number")
    .slice(0, PREFETCH_TOP_N)
    .join(",");

  useEffect(() => {
    if (!key) return;
    for (const id of key.split(",").map(Number)) {
      if (peek(`cluster:${id}`, maxAgeMs) !== undefined) continue; // already warm — don't refetch
      void revalidate(`cluster:${id}`, () => getCluster(id)).catch(() => {});
    }
  }, [key, maxAgeMs]);
}
