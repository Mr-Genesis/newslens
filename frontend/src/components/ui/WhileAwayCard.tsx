"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getDigest, type Digest } from "@/lib/api";
import { storyHref } from "@/lib/utils";
import { useEventStream } from "@/hooks/useEventStream";

/** "While you were away" (Wave C): the in-app return trigger. Shows clusters formed since the
 *  last visit with their cached WIIFM headline. Hidden when caught up. */
export function WhileAwayCard() {
  const [digest, setDigest] = useState<Digest | null>(null);

  const refresh = useCallback(() => {
    getDigest()
      .then(setDigest)
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // #102: live-refresh when the backend signals new content (feed_refresh / new_cluster).
  useEventStream(
    useCallback(
      (type: string) => {
        if (type === "feed_refresh" || type === "new_cluster") refresh();
      },
      [refresh]
    )
  );

  if (!digest || digest.count === 0) return null;

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--accent-muted)] bg-[var(--accent-subtle)] p-[var(--space-md)] mb-6">
      <div className="text-mono text-[var(--accent)] mb-2">WHILE YOU WERE AWAY</div>
      <div className="flex flex-col gap-2.5">
        {digest.items.map((i) => (
          <Link key={i.cluster_id} href={storyHref(i.cluster_id)} className="block">
            <p className="text-small text-[var(--text-primary)] leading-snug">{i.title}</p>
            {i.headline && (
              <p className="text-mono text-[10px] text-[var(--accent)] mt-0.5">{i.headline}</p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
