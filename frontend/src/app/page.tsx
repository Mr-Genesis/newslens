"use client";

import { useEffect, useState, useCallback } from "react";
import { NavBar } from "@/components/layout/NavBar";
import { StoryCard } from "@/components/StoryCard";
import { StoryCardSkeleton } from "@/components/ui/Skeleton";
import { getBriefing, type Briefing, type BriefingStory } from "@/lib/api";
import { relativeTime, isStale } from "@/lib/utils";
import { cn } from "@/lib/utils";

type PageState = "loading" | "success" | "error" | "empty" | "refreshing";

export default function BriefingPage() {
  const [state, setState] = useState<PageState>("loading");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchBriefing = useCallback(async (isRefresh = false) => {
    try {
      setState(isRefresh ? "refreshing" : "loading");
      setError(null);
      const data = await getBriefing();

      if (!data.stories || data.stories.length === 0) {
        setState("empty");
        return;
      }

      setBriefing(data);
      setState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load briefing");
      setState("error");
    }
  }, []);

  useEffect(() => {
    fetchBriefing();
  }, [fetchBriefing]);

  // Group stories by category
  const grouped = briefing?.stories.reduce<Record<string, BriefingStory[]>>(
    (acc, story) => {
      const cat = story.category || "General";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(story);
      return acc;
    },
    {}
  );

  return (
    <>
      <NavBar />
      <main className="flex-1 mx-auto max-w-[640px] w-full px-[var(--space-md)] pb-[var(--space-3xl)]">
        {/* Header with timestamp */}
        {briefing && state === "success" && (
          <div className="flex items-center justify-between pt-[var(--space-lg)] pb-[var(--space-sm)]">
            <h1 className="text-hero text-[var(--text-primary)]">
              Daily Briefing
            </h1>
            <span
              className={cn(
                "text-mono",
                isStale(briefing.generated_at)
                  ? "text-[var(--accent)]"
                  : "text-[var(--text-ghost)]"
              )}
            >
              {relativeTime(briefing.generated_at)}
            </span>
          </div>
        )}

        {/* Loading state */}
        {state === "loading" && (
          <div className="pt-[var(--space-lg)]">
            <div className="h-8 w-48 skeleton mb-4" />
            {[1, 2, 3, 4, 5].map((i) => (
              <StoryCardSkeleton key={i} />
            ))}
          </div>
        )}

        {/* Empty / first-run state */}
        {state === "empty" && (
          <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
            <div className="w-3 h-3 rounded-full bg-[var(--accent)] animate-pulse mb-4" />
            <p className="text-body text-[var(--text-muted)]">
              Setting up your feed...
            </p>
            <p className="text-small text-[var(--text-ghost)] mt-2">
              Articles are being fetched and analyzed. Check back in a few minutes.
            </p>
          </div>
        )}

        {/* Error state */}
        {state === "error" && (
          <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
            <p className="text-body text-[var(--text-secondary)]">
              Couldn&apos;t load briefing
            </p>
            {error && (
              <p className="text-mono text-[var(--dismiss)] mt-2">{error}</p>
            )}
            <button
              onClick={() => fetchBriefing()}
              className="mt-4 px-4 py-2 rounded-[var(--radius-sm)] bg-[var(--surface-raised)] text-small text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Success: stories grouped by category */}
        {(state === "success" || state === "refreshing") && grouped && (
          <div className={cn(state === "refreshing" && "opacity-80")}>
            {Object.entries(grouped).map(([category, stories]) => (
              <section key={category} className="mt-[var(--space-lg)]">
                <h2 className="text-category text-[var(--text-muted)] mb-[var(--space-sm)]">
                  {category}
                </h2>
                {stories.map((story) => (
                  <StoryCard key={story.cluster_id} story={story} />
                ))}
              </section>
            ))}

            {/* Refresh button */}
            <div className="flex justify-center pt-[var(--space-xl)]">
              <button
                onClick={() => fetchBriefing(true)}
                disabled={state === "refreshing"}
                className="px-4 py-2 rounded-[var(--radius-sm)] bg-[var(--surface)] text-mono text-[var(--text-muted)] hover:bg-[var(--surface-raised)] transition-colors disabled:opacity-50"
              >
                {state === "refreshing" ? "Refreshing..." : "Refresh briefing"}
              </button>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
