"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { getClusterImpact, type LensResult } from "@/lib/api";

interface Dimension {
  key: string;
  label: string;
  body: string;
}

const ClockIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

/** "What's in it for me" — personalised impact, amber. Data: GET /clusters/{id}/impact.
 *  Hides itself when the lens is unavailable (graceful degradation). */
export function ImpactCard({ clusterId }: { clusterId: number }) {
  const [data, setData] = useState<LensResult | "loading">("loading");

  useEffect(() => {
    let alive = true;
    getClusterImpact(clusterId)
      .then((r) => alive && setData(r))
      .catch(() => alive && setData({ unavailable: true }));
    return () => {
      alive = false;
    };
  }, [clusterId]);

  if (data === "loading") {
    return <div className="skeleton h-24 rounded-[var(--radius-lg)]" />;
  }
  // When the only thing missing is the user's profession, invite them to set it
  // instead of silently hiding — this lens is the payoff for filling it in.
  if (data.reason === "profession_unset") {
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
  if (data.unavailable) return null;

  const headline = typeof data.headline === "string" ? data.headline : null;
  const dims = Array.isArray(data.dimensions) ? (data.dimensions as Dimension[]) : [];
  if (!headline && dims.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-[var(--radius-lg)] border border-[var(--accent-muted)] bg-[var(--accent-subtle)] p-[var(--space-md)]"
    >
      <div className="flex items-center gap-1.5 text-mono text-[var(--accent)] mb-2">
        <ClockIcon />
        WHAT&apos;S IN IT FOR ME
      </div>
      {headline && (
        <p className="text-small text-[var(--text-primary)] leading-relaxed">{headline}</p>
      )}
      {dims.length > 0 && (
        <dl className="mt-3 flex flex-col gap-2">
          {dims.map((d) => (
            <div key={d.key}>
              <dt className="text-mono text-[10px] uppercase text-[var(--accent)]">{d.label}</dt>
              <dd className="text-small text-[var(--text-secondary)]">{d.body}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="text-mono text-[10px] text-[var(--text-ghost)] mt-3">
        AI-generated &middot; personalised to your profile
      </p>
    </motion.div>
  );
}
