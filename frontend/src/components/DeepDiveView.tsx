"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { AISummaryBox } from "@/components/ui/AISummaryBox";
import { SourceCard } from "@/components/SourceCard";
import { SourceSpectrum } from "@/components/SourceSpectrum";
import { StoryActionBar } from "@/components/StoryActionBar";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { Button } from "@/components/ui/Button";
import { DeepDiveSkeleton } from "@/components/ui/Skeleton";
import { relativeTime } from "@/lib/utils";
import { getCluster, type ClusterDetail } from "@/lib/api";

type PageState = "loading" | "success" | "error";

const topicColorMap: Record<string, string> = {
  technology: "var(--topic-tech)",
  tech: "var(--topic-tech)",
  politics: "var(--topic-politics)",
  business: "var(--topic-business)",
  science: "var(--topic-science)",
  sports: "var(--topic-sports)",
  health: "var(--topic-health)",
  world: "var(--topic-world)",
};

function getTopicColor(category: string): string {
  const lower = category.toLowerCase();
  return topicColorMap[lower] || "var(--topic-default)";
}

export default function DeepDiveView({
  clusterIdOverride,
}: { clusterIdOverride?: number } = {}) {
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

  // Get first article ID for action bar feedback
  const firstArticleId = cluster?.sources?.[0]?.article?.id;

  // Infer category from first source's topics or fallback
  const category =
    cluster?.sources?.[0]?.article?.source?.name || "News";

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)] pb-[80px]">
      {/* Loading */}
      {state === "loading" && (
        <div className="pt-[var(--space-md)]">
          <DeepDiveSkeleton />
        </div>
      )}

      {/* Error */}
      {state === "error" && (
        <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
          <div className="w-12 h-12 rounded-full bg-[var(--dismiss-muted)] flex items-center justify-center mb-4">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--dismiss)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <p className="text-heading text-[var(--text-primary)]">
            Couldn&apos;t load story details
          </p>
          {error && (
            <p className="text-mono text-[var(--dismiss)] mt-2">{error}</p>
          )}
          <Button variant="secondary" onClick={fetchCluster} className="mt-4">
            Try again
          </Button>
        </div>
      )}

      {/* Success */}
      {state === "success" && cluster && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
            className="pt-[var(--space-md)]"
          >
            {/* Hero section */}
            <div className="mb-4">
              {/* Category + timestamp + confidence */}
              <div className="flex items-center gap-2 mb-2">
                <Badge
                  variant="topic"
                  size="md"
                  color={getTopicColor(category)}
                >
                  {category}
                </Badge>
                <span className="text-mono text-[var(--text-ghost)]">
                  {relativeTime(cluster.created_at)}
                </span>
              </div>

              {/* Title */}
              <motion.h1
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.1 }}
                className="text-hero text-[var(--text-primary)]"
              >
                {cluster.title}
              </motion.h1>

              {/* Confidence */}
              <div className="mt-3">
                <ConfidenceScore
                  sourceCount={cluster.sources.length}
                  coherence={0.85}
                />
              </div>
            </div>

            {/* AI Summary — tabbed */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.15 }}
              className="mb-4"
            >
              <AISummaryBox summary={cluster.summary} coherence={0.85} />
            </motion.div>

            {/* Source Spectrum */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.2 }}
              className="mb-4"
            >
              <SourceSpectrum
                freeCount={freeCount}
                paywallCount={paywallCount}
              />
            </motion.div>

            {/* Sources header */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.25 }}
              className="mb-3"
            >
              <h2 className="text-category text-[var(--text-muted)]">
                Sources
              </h2>
            </motion.div>

            {/* Source cards */}
            <div>
              {sortedSources.map((sourceCard, index) => (
                <SourceCard
                  key={sourceCard.article.id}
                  sourceName={sourceCard.article.source.name}
                  url={sourceCard.article.url}
                  snippet={sourceCard.article.snippet}
                  isFree={sourceCard.is_free}
                  publishedAt={sourceCard.article.published_at}
                  index={index}
                />
              ))}
            </div>
          </motion.div>

          {/* Floating action bar */}
          {firstArticleId && (
            <StoryActionBar articleId={firstArticleId} />
          )}
        </>
      )}
    </div>
  );
}
