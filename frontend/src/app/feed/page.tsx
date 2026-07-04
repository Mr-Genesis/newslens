"use client";

import { useState } from "react";
import { Chip } from "@/components/ui/Chip";
import { InfiniteFeed } from "@/components/InfiniteFeed";

type SourceType = "all" | "news" | "research" | "expert" | "official" | "filing";
const CHIPS: { label: string; value: SourceType }[] = [
  { label: "All", value: "all" },
  { label: "News", value: "news" },
  { label: "Research", value: "research" },
  { label: "Experts", value: "expert" },
  { label: "Official", value: "official" },
  // Filings surface only a user's watchlisted companies (audience=[]); the chip is empty until they
  // watchlist a company — the intended, honest behaviour, not a bug.
  { label: "Filings", value: "filing" },
];

/** #82 / WS-3 (#113) — the source-type-filtered feed screen, now infinite-scrolling via the shared
 *  InfiniteFeed (cursor pagination + prefetch + dedupe). Switching a chip remounts the feed. */
export default function FeedPage() {
  const [active, setActive] = useState<SourceType>("all");
  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)] pt-2">
      <h1 className="text-hero text-[var(--text-primary)] mb-3">Feed</h1>
      <div className="flex gap-2 overflow-x-auto pb-3 -mx-4 px-4" role="group" aria-label="Filter by source type">
        {CHIPS.map((c) => (
          <Chip key={c.value} selected={active === c.value} onClick={() => setActive(c.value)}>
            {c.label}
          </Chip>
        ))}
      </div>

      <InfiniteFeed
        key={active}
        surface="feed"
        sourceType={active === "all" ? undefined : active}
        emptyLabel="Nothing here yet — check back soon."
      />
    </div>
  );
}
