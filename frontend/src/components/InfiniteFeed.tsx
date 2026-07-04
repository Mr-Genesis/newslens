"use client";

/**
 * WS-3 (#113): the "All stories" infinite feed. Wraps useInfiniteFeed and renders FeedArticleCard
 * rows with impression logging, a scroll sentinel, three loading skeletons, an inline retry, and a
 * "You're all caught up" terminal. Reused on the home briefing and the /feed screen.
 *
 * Cross-section dedupe (home): `excludeClusterIds` filters out any story already shown above (hero >
 * rails > categories), so one story renders once. The filter runs at render, so ids that arrive late
 * (rails self-fetch) still de-dup on the next paint.
 */
import { useMemo } from "react";

import { FeedArticleCard } from "@/components/FeedArticleCard";
import { Button } from "@/components/ui/Button";
import { useInfiniteFeed } from "@/hooks/useInfiniteFeed";
import { useImpressions } from "@/hooks/useImpressions";
import type { ImpressionItem } from "@/lib/api";

interface InfiniteFeedProps {
  surface?: ImpressionItem["surface"];
  sourceType?: string;
  topicId?: number;
  perPage?: number;
  /** Cluster ids already rendered above on the same screen — filtered out (cross-section dedupe). */
  excludeClusterIds?: Set<number>;
  /** Render the "ALL STORIES" chapter break above the feed (home). */
  showHeader?: boolean;
  /** Shown when the feed is genuinely empty. Home omits it (stay silent); /feed passes a message. */
  emptyLabel?: string;
}

function FeedRowSkeleton() {
  return (
    <div className="py-4 border-b border-[var(--border-subtle)]">
      <div className="h-5 w-3/4 skeleton mb-2" />
      <div className="h-4 w-full skeleton mb-1" />
      <div className="h-3 w-24 skeleton" />
    </div>
  );
}

function AllStoriesHeader() {
  return (
    <div className="mt-6 mb-3">
      <div className="flex items-center gap-3">
        <h2 className="text-category text-[var(--text-muted)] whitespace-nowrap">ALL STORIES</h2>
        <span className="flex-1 h-px bg-[var(--border-subtle)]" aria-hidden />
      </div>
      <p className="text-small text-[var(--text-ghost)] mt-1">Everything, newest first</p>
    </div>
  );
}

export function InfiniteFeed({
  surface = "feed",
  sourceType,
  topicId,
  perPage = 20,
  excludeClusterIds,
  showHeader = false,
  emptyLabel,
}: InfiniteFeedProps) {
  const { items, status, sentinelRef, retry } = useInfiniteFeed({ perPage, topicId, sourceType });
  const { observe } = useImpressions(surface);

  const visible = useMemo(
    () =>
      excludeClusterIds
        ? items.filter((a) => a.cluster_id == null || !excludeClusterIds.has(a.cluster_id))
        : items,
    [items, excludeClusterIds]
  );

  // Initial load (no items yet): three skeletons.
  if (status === "loading" && items.length === 0) {
    return (
      <div aria-label="Loading stories" aria-busy>
        {showHeader && <AllStoriesHeader />}
        {[0, 1, 2].map((i) => (
          <FeedRowSkeleton key={i} />
        ))}
      </div>
    );
  }

  // Initial load failed (no items): retry, don't blank the briefing.
  if (status === "error" && items.length === 0) {
    return (
      <div className="py-6 text-center">
        <p className="text-small text-[var(--dismiss)]">Couldn&apos;t load more stories.</p>
        <Button variant="secondary" size="sm" onClick={retry} className="mt-3">
          Try again
        </Button>
      </div>
    );
  }

  // Nothing to show. On a dedicated feed screen, say so (emptyLabel); on home, stay silent (the feed
  // just added nothing the sections above didn't already show).
  if (status === "done" && visible.length === 0) {
    return emptyLabel ? (
      <p className="text-small text-[var(--text-muted)] pt-6">{emptyLabel}</p>
    ) : null;
  }

  return (
    <section aria-label="All stories">
      {showHeader && <AllStoriesHeader />}
      <div className="flex flex-col">
        {visible.map((a) => (
          <div
            key={a.id}
            ref={observe}
            data-impression-cluster={a.cluster_id ?? undefined}
            data-impression-article={a.cluster_id ? undefined : a.id}
            onClickCapture={() => sessionStorage.setItem("nl_surface", surface)}
          >
            <FeedArticleCard article={a} />
          </div>
        ))}
      </div>

      {status === "paging" && (
        <p className="text-mono text-[var(--text-muted)] text-center py-4">Loading more…</p>
      )}
      {status === "error" && items.length > 0 && (
        <div className="py-4 text-center">
          <Button variant="ghost" size="sm" onClick={retry}>
            Retry
          </Button>
        </div>
      )}
      {status === "done" && (
        <p className="text-mono text-[var(--text-ghost)] text-center py-6">You&apos;re all caught up</p>
      )}
      {/* The sentinel: present only while more can load. */}
      {(status === "idle" || status === "paging") && (
        <div ref={sentinelRef} aria-hidden className="h-1 w-full" />
      )}
    </section>
  );
}
