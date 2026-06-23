"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  getClusterImpact,
  isStoryImpact,
  type ImpactResult,
  type ImpactDimension,
  type Horizon,
  type ImpactConfidence,
} from "@/lib/api";
import { IMPACT_SEEN_KEY } from "@/components/ui/PersonalizeBanner";

const ClockIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const HORIZON_LABEL: Record<Horizon, string> = {
  now: "NOW",
  weeks: "WEEKS",
  quarter: "QUARTER",
  year_plus: "YEAR+",
};

const DIMENSIONS: { key: keyof StoryImpactDims; label: string }[] = [
  { key: "professional", label: "PROFESSION" },
  { key: "financial", label: "MONEY" },
  { key: "civic", label: "CIVIC" },
];

type StoryImpactDims = {
  professional: ImpactDimension;
  financial: ImpactDimension;
  civic: ImpactDimension;
};

function confidenceColor(c: ImpactConfidence): string {
  return c === "high" ? "var(--agree)" : c === "medium" ? "var(--accent)" : "var(--text-ghost)";
}

/** "What's in it for me" — per-persona impact. Data: GET /clusters/{id}/impact.
 *  Accepts an optional pre-fetched `data` (so the Deep Dive lead + this card share one
 *  request); otherwise self-fetches. Hides itself when the lens is unavailable. */
export function ImpactCard({
  clusterId,
  data: provided,
}: {
  clusterId: number;
  data?: ImpactResult | null;
}) {
  const reduce = useReducedMotion();
  const [fetched, setFetched] = useState<ImpactResult | "loading" | null>(
    provided ?? "loading"
  );

  useEffect(() => {
    if (provided !== undefined) {
      setFetched(provided);
      return;
    }
    let alive = true;
    getClusterImpact(clusterId)
      .then((r) => alive && setFetched(r))
      .catch(() => alive && setFetched({ unavailable: true }));
    return () => {
      alive = false;
    };
  }, [clusterId, provided]);

  const data = fetched;

  // Mark that the user met an impact card needing a profession → unlocks the
  // "Personalize your impact lens" banner on Today (E3).
  useEffect(() => {
    if (
      data && data !== "loading" && "reason" in data &&
      data.reason === "profession_unset" && typeof window !== "undefined"
    ) {
      localStorage.setItem(IMPACT_SEEN_KEY, "1");
    }
  }, [data]);

  if (data === "loading" || data === null) {
    return <div className="skeleton h-24 rounded-[var(--radius-lg)]" />;
  }

  // Invite the reader to personalize when the only thing missing is their profession.
  if (!isStoryImpact(data) && data.reason === "profession_unset") {
    return (
      <Link
        href="/settings"
        className="block rounded-[var(--radius-lg)] border border-[var(--accent-muted)] bg-[var(--accent-subtle)] p-[var(--space-md)] transition-colors hover:bg-[var(--accent-muted)]"
      >
        <div className="flex items-center gap-1.5 text-mono text-[var(--accent)] mb-2">
          <ClockIcon />
          WHAT&apos;S IN IT FOR ME
        </div>
        <p className="text-small text-[var(--text-primary)] leading-relaxed">
          Personalize this — set your profession &rarr;
        </p>
      </Link>
    );
  }

  // Any other unavailable reason degrades gracefully (hidden).
  if (!isStoryImpact(data)) return null;

  const score = data.personal_relevance.score;
  const band = score >= 70 ? "high" : score >= 40 ? "notable" : "low";
  const bandColor =
    band === "high" ? "var(--accent)" : band === "notable" ? "var(--text-secondary)" : "var(--text-ghost)";
  const bandLabel = band === "high" ? "HIGH" : band === "notable" ? "NOTABLE" : "LOW";

  const dims = DIMENSIONS.map((d) => ({ ...d, dim: data.dimensions[d.key] })).filter(
    (d) => d.dim && d.dim.applicable
  );

  if (dims.length === 0 && !data.headline) return null;

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={reduce ? {} : { opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      // Low-relevance stories render dimmed (honest, not hidden).
      style={{ opacity: band === "low" ? 0.72 : 1 }}
      className="rounded-[var(--radius-lg)] border border-[var(--accent-muted)] bg-[var(--accent-subtle)] p-[var(--space-md)]"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 text-mono text-[var(--accent)]">
          <ClockIcon />
          WHAT&apos;S IN IT FOR ME
        </div>
        {/* relevance band chip — value shown as text, not color alone (a11y) */}
        <span
          className="text-mono px-2 py-0.5 rounded-[var(--radius-sm)] bg-[var(--surface-raised)]"
          style={{ color: bandColor }}
        >
          {score} · {bandLabel} FOR YOU
        </span>
      </div>

      {data.headline && (
        <p className="text-small text-[var(--text-primary)] leading-relaxed">{data.headline}</p>
      )}

      <div className="mt-3 flex flex-col gap-2.5">
        {dims.map(({ key, label, dim }) => (
          <div
            key={key}
            className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--surface)] p-3"
          >
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-mono text-[10px] uppercase text-[var(--text-secondary)]">
                {label}
              </span>
              <span className="flex items-center gap-2">
                <span className="text-mono text-[10px] text-[var(--text-muted)]">
                  {HORIZON_LABEL[dim.horizon]}
                </span>
                <span className="flex items-center gap-1 text-mono text-[10px] text-[var(--text-muted)]">
                  <span
                    className="inline-block w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: confidenceColor(dim.confidence) }}
                  />
                  {dim.confidence.toUpperCase()}
                </span>
              </span>
            </div>
            {dim.relevance && (
              <p className="text-small text-[var(--text-primary)] leading-snug">{dim.relevance}</p>
            )}
            {dim.mechanism && (
              <p className="text-small text-[var(--text-secondary)] leading-snug mt-1">
                {dim.mechanism}
              </p>
            )}
            {dim.watch_items.length > 0 && (
              <p className="text-mono text-[10px] text-[var(--text-muted)] mt-2">
                WATCH · {dim.watch_items.join(" · ")}
              </p>
            )}
            {key === "financial" && (
              <p className="text-mono text-[10px] text-[var(--text-ghost)] mt-2">
                Not financial advice — exposure &amp; signals only.
              </p>
            )}
          </div>
        ))}
      </div>

      {data.caveats && (
        <p className="text-mono text-[10px] text-[var(--text-ghost)] mt-3">{data.caveats}</p>
      )}
      <p className="text-mono text-[10px] text-[var(--text-ghost)] mt-2">
        AI-generated &middot; personalised to your profile
      </p>
    </motion.div>
  );
}
