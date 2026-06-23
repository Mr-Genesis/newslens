"use client";

import { motion } from "framer-motion";
import { relativeTime } from "@/lib/utils";

interface AgreementMeterProps {
  coherence: number;
  sourceCount: number;
  createdAt: string;
}

/** Deep Dive cluster meter — "Source overlap" + % + bar, tier-coloured.
 *  HONEST LABEL (Wave A): the value is embedding tightness — how tightly the sources
 *  cluster onto the same story — NOT whether they agree. We no longer assert "agreement"
 *  (a claim we don't measure). A real consensus/divergence metric lands in Wave B. */
function tier(coherence: number): { pct: number; color: string } {
  const pct = Math.round(coherence * 100);
  if (coherence >= 0.8) return { pct, color: "var(--agree)" };
  if (coherence >= 0.6) return { pct, color: "var(--warning)" };
  return { pct, color: "var(--text-muted)" };
}

export function AgreementMeter({
  coherence,
  sourceCount,
  createdAt,
}: AgreementMeterProps) {
  const { pct, color } = tier(coherence);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-small text-[var(--text-secondary)]">
          Source overlap
        </span>
        <span className="text-mono" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-[var(--surface-raised)] overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
        />
      </div>
      <span className="text-mono text-[var(--text-ghost)]">
        {sourceCount} {sourceCount === 1 ? "outlet" : "outlets"} &middot;{" "}
        {relativeTime(createdAt)}
      </span>
    </div>
  );
}
