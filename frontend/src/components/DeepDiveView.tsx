"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { AISummaryBox } from "@/components/ui/AISummaryBox";
import { ImpactCard } from "@/components/ui/ImpactCard";
import { AskBox } from "@/components/ui/AskBox";
import { Collapsible } from "@/components/ui/Collapsible";
import { FrameworksCard } from "@/components/ui/FrameworksCard";
import { EntityChips } from "@/components/ui/EntityChips";
import { ConsensusRow } from "@/components/ui/ConsensusRow";
import { TriviaCard } from "@/components/ui/TriviaCard";
import { SourceCard } from "@/components/SourceCard";
import { SourceSpectrum } from "@/components/SourceSpectrum";
import { IconButton } from "@/components/ui/IconButton";
import { AgreementMeter } from "@/components/ui/AgreementMeter";
import { Button } from "@/components/ui/Button";
import { DeepDiveSkeleton } from "@/components/ui/Skeleton";
import {
  getCluster,
  getClusterImpact,
  isStoryImpact,
  postFeedback,
  type ClusterDetail,
  type ImpactResult,
} from "@/lib/api";

type PageState = "loading" | "success" | "error";

/** First sentence of the summary — the lead falls back to this when the impact
 *  engine has no one-liner yet (no profession / no key / still generating). */
function firstSentence(s: string | null): string {
  if (!s) return "";
  const m = s.match(/^[\s\S]*?[.!?](\s|$)/);
  return (m ? m[0] : s).trim();
}

const ShareIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
    <polyline points="16 6 12 2 8 6" />
    <line x1="12" y1="2" x2="12" y2="15" />
  </svg>
);

const BookmarkIcon = ({ filled }: { filled: boolean }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </svg>
);

export default function DeepDiveView({
  clusterIdOverride,
}: { clusterIdOverride?: number } = {}) {
  const params = useParams();
  const clusterId = clusterIdOverride ?? Number(params.clusterId);

  const [state, setState] = useState<PageState>("loading");
  const [cluster, setCluster] = useState<ClusterDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [impact, setImpact] = useState<ImpactResult | null>(null);
  const [expandAll, setExpandAll] = useState(false); // BRIEF / FULL toggle (v4)

  // One impact fetch shared by the lead sentence + the ImpactCard.
  useEffect(() => {
    if (!clusterId || isNaN(clusterId)) return;
    let alive = true;
    getClusterImpact(clusterId)
      .then((r) => alive && setImpact(r))
      .catch(() => alive && setImpact({ unavailable: true }));
    return () => {
      alive = false;
    };
  }, [clusterId]);

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
      setError(err instanceof Error ? err.message : "Failed to load story details");
      setState("error");
    }
  }, [clusterId]);

  useEffect(() => {
    fetchCluster();
  }, [fetchCluster]);

  const sortedSources = cluster?.sources
    ? [...cluster.sources].sort((a, b) => {
        if (a.is_free !== b.is_free) return a.is_free ? -1 : 1;
        return a.article.source.name.localeCompare(b.article.source.name);
      })
    : [];
  const freeCount = sortedSources.filter((s) => s.is_free).length;
  const paywallCount = sortedSources.filter((s) => !s.is_free).length;
  const firstArticleId = cluster?.sources?.[0]?.article?.id;

  async function handleSave() {
    if (!firstArticleId) return;
    setSaved((s) => !s);
    try {
      await postFeedback(firstArticleId, "save");
    } catch {
      /* ignore */
    }
  }

  async function handleShare() {
    const url = typeof window !== "undefined" ? window.location.href : "";
    try {
      if (navigator.share) {
        await navigator.share({ title: cluster?.title ?? "NewsLens", url });
      } else {
        await navigator.clipboard.writeText(url);
      }
      if (firstArticleId) await postFeedback(firstArticleId, "share");
    } catch {
      /* user cancelled */
    }
  }

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)] pb-[var(--space-2xl)]">
      {state === "loading" && (
        <div className="pt-[var(--space-md)]">
          <DeepDiveSkeleton />
        </div>
      )}

      {state === "error" && (
        <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
          <p className="text-heading text-[var(--text-primary)]">
            Couldn&apos;t load this story
          </p>
          {error && <p className="text-mono text-[var(--text-muted)] mt-2">{error}</p>}
          <Button variant="secondary" onClick={fetchCluster} className="mt-4">
            Try again
          </Button>
        </div>
      )}

      {state === "success" && cluster && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="pt-[var(--space-md)] flex flex-col gap-4"
        >
          {/* Top actions */}
          <div className="flex justify-end gap-1">
            <IconButton label="Share" onClick={handleShare}>
              <ShareIcon />
            </IconButton>
            <IconButton
              label={saved ? "Saved" : "Save"}
              variant={saved ? "accent" : "default"}
              onClick={handleSave}
            >
              <BookmarkIcon filled={saved} />
            </IconButton>
          </div>

          {/* Hero */}
          <div>
            <p className="text-mono text-[var(--accent)] mb-2">AI &middot; DEEP DIVE</p>
            <motion.h1
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
              className="text-hero text-[var(--text-primary)]"
            >
              {cluster.title}
            </motion.h1>

            {/* The "so what" lead — impact one-liner, else the summary's first sentence */}
            {(() => {
              const lead =
                isStoryImpact(impact) && impact.personal_relevance.one_liner
                  ? impact.personal_relevance.one_liner
                  : firstSentence(cluster.summary);
              return lead ? (
                <p className="text-title italic text-[var(--text-primary)] mt-3 pl-3 border-l-2 border-[var(--accent)]">
                  {lead}
                </p>
              ) : null;
            })()}

            {/* Relevance band chip — value shown as text, not colour alone (a11y) */}
            {isStoryImpact(impact) && (
              <div className="mt-2">
                {(() => {
                  const s = impact.personal_relevance.score;
                  const color =
                    s >= 70 ? "var(--accent)" : s >= 40 ? "var(--text-secondary)" : "var(--text-ghost)";
                  const lbl = s >= 70 ? "HIGH" : s >= 40 ? "NOTABLE" : "LOW";
                  return (
                    <span
                      className="text-mono px-2 py-0.5 rounded-[var(--radius-sm)] bg-[var(--surface-raised)]"
                      style={{ color }}
                    >
                      {s} · {lbl} FOR YOU
                    </span>
                  );
                })()}
              </div>
            )}

            <div className="mt-4">
              <AgreementMeter
                coherence={cluster.coherence}
                sourceCount={cluster.sources.length}
                createdAt={cluster.created_at}
              />
            </div>
          </div>

          {/* BRIEF / FULL toggle (v4: brief by default, deep on tap) */}
          <div className="flex justify-end">
            <div className="inline-flex rounded-[var(--radius-md)] border border-[var(--border)] overflow-hidden text-mono">
              <button
                type="button"
                onClick={() => setExpandAll(false)}
                className={
                  !expandAll
                    ? "bg-[var(--surface-raised)] text-[var(--text-primary)] px-3 py-1"
                    : "text-[var(--text-muted)] px-3 py-1"
                }
              >
                BRIEF
              </button>
              <button
                type="button"
                onClick={() => setExpandAll(true)}
                className={
                  expandAll
                    ? "bg-[var(--surface-raised)] text-[var(--text-primary)] px-3 py-1"
                    : "text-[var(--text-muted)] px-3 py-1"
                }
              >
                FULL
              </button>
            </div>
          </div>

          {/* Brief-by-default accordion (key flips on BRIEF/FULL to expand/collapse all) */}
          <div className="flex flex-col">
            <Collapsible key={`sum-${expandAll}`} label="SUMMARY" preview={firstSentence(cluster.summary)} defaultOpen={expandAll}>
              <AISummaryBox summary={cluster.summary} coherence={cluster.coherence} clusterId={clusterId} />
            </Collapsible>
            <Collapsible key={`you-${expandAll}`} label="FOR YOU" preview="What this means for you" defaultOpen={expandAll}>
              <ImpactCard clusterId={clusterId} data={impact} />
            </Collapsible>
            <Collapsible key={`con-${expandAll}`} label="CONSENSUS" preview="Where sources agree & diverge" defaultOpen={expandAll}>
              <ConsensusRow clusterId={clusterId} />
            </Collapsible>
            <Collapsible key={`fw-${expandAll}`} label="FRAMEWORKS" preview="How to read this story" defaultOpen={expandAll}>
              <FrameworksCard clusterId={clusterId} />
            </Collapsible>
            <Collapsible key={`ent-${expandAll}`} label="IN THIS STORY" preview="People, orgs & places" defaultOpen={expandAll}>
              <EntityChips clusterId={clusterId} />
            </Collapsible>
            <Collapsible key={`src-${expandAll}`} label="SOURCES" preview={`${freeCount} free · ${paywallCount} paywall`} defaultOpen={expandAll}>
              <SourceSpectrum freeCount={freeCount} paywallCount={paywallCount} />
              <div className="flex flex-col">
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
            </Collapsible>
          </div>

          {/* Quiz */}
          <TriviaCard clusterId={clusterId} />

          {/* Ask this story (Wave B1) */}
          <AskBox clusterId={clusterId} />
        </motion.div>
      )}
    </div>
  );
}
