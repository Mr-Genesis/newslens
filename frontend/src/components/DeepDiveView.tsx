"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { NavBar } from "@/components/layout/NavBar";
import { AISummaryBox } from "@/components/ui/AISummaryBox";
import { SourceCard } from "@/components/SourceCard";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { DeepDiveSkeleton } from "@/components/ui/Skeleton";
import { getCluster, type ClusterDetail } from "@/lib/api";

type PageState = "loading" | "success" | "error";

export default function DeepDiveView({ clusterIdOverride }: { clusterIdOverride?: number } = {}) {
  const params = useParams();
  const router = useRouter();
  const clusterId = clusterIdOverride ?? Number(params.clusterId);

  const [state, setState] = useState<PageState>("loading");
  const [cluster, setCluster] = useState<ClusterDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchCluster = useCallback(async () => {
    if (!clusterId || isNaN(clusterId)) {
      setError("Invalid story ID");
      setState("error");
      return;
    }

    try {
      setState("loading");
      setError(null);
      const data = await getCluster(clusterId);
      setCluster(data);
      setState("success");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load story details"
      );
      setState("error");
    }
  }, [clusterId]);

  useEffect(() => {
    fetchCluster();
  }, [fetchCluster]);

  // Sort sources: free first, then paywalled, alphabetical within each group
  const sortedSources = cluster?.sources
    ? [...cluster.sources].sort((a, b) => {
        if (a.is_free !== b.is_free) {
          return a.is_free ? -1 : 1;
        }
        return a.article.source.name.localeCompare(b.article.source.name);
      })
    : [];

  const freeCount = sortedSources.filter((s) => s.is_free).length;
  const paywallCount = sortedSources.filter((s) => !s.is_free).length;

  return (
    <>
      <NavBar />
      <main className="flex-1 mx-auto max-w-[640px] w-full px-[var(--space-md)] pb-[var(--space-3xl)]">
        {/* Back button */}
        <button
          onClick={() => router.back()}
          className="flex items-center gap-1 pt-[var(--space-lg)] pb-[var(--space-sm)] text-small text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
        >
          <span>&larr;</span>
          <span>Back</span>
        </button>

        {/* Loading */}
        {state === "loading" && (
          <div className="pt-[var(--space-md)]">
            <DeepDiveSkeleton />
          </div>
        )}

        {/* Error */}
        {state === "error" && (
          <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
            <p className="text-body text-[var(--text-secondary)]">
              Couldn&apos;t load story details
            </p>
            {error && (
              <p className="text-mono text-[var(--dismiss)] mt-2">{error}</p>
            )}
            <button
              onClick={fetchCluster}
              className="mt-4 px-4 py-2 rounded-[var(--radius-sm)] bg-[var(--surface-raised)] text-small text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Success */}
        {state === "success" && cluster && (
          <div className="pt-[var(--space-md)]">
            {/* Title */}
            <h1 className="text-hero text-[var(--text-primary)]">
              {cluster.title}
            </h1>

            {/* Confidence */}
            <div className="mt-2">
              <ConfidenceScore
                sourceCount={cluster.sources.length}
                coherence={0.85}
              />
            </div>

            {/* AI Summary */}
            <div className="mt-[var(--space-lg)]">
              <AISummaryBox
                summary={cluster.summary}
                coherence={0.85}
              />
            </div>

            {/* Source count summary */}
            <div className="mt-[var(--space-xl)] flex items-center gap-3">
              <h2 className="text-category text-[var(--text-muted)]">
                Sources
              </h2>
              <span className="text-mono text-[var(--text-ghost)]">
                {freeCount} free &middot; {paywallCount} paywalled
              </span>
            </div>

            {/* Source cards */}
            <div className="mt-[var(--space-sm)]">
              {sortedSources.map((sourceCard) => (
                <SourceCard
                  key={sourceCard.article.id}
                  sourceName={sourceCard.article.source.name}
                  url={sourceCard.article.url}
                  snippet={sourceCard.article.snippet}
                  isFree={sourceCard.is_free}
                />
              ))}
            </div>
          </div>
        )}
      </main>
    </>
  );
}
