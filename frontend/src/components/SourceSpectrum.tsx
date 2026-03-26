"use client";

import { motion } from "framer-motion";

interface SourceSpectrumProps {
  freeCount: number;
  paywallCount: number;
}

export function SourceSpectrum({
  freeCount,
  paywallCount,
}: SourceSpectrumProps) {
  const total = freeCount + paywallCount;
  if (total === 0) return null;

  const freePct = (freeCount / total) * 100;
  const paywallPct = (paywallCount / total) * 100;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-mono text-[var(--text-ghost)]">
          Source access
        </span>
        <span className="text-mono text-[var(--text-ghost)]">
          {total} source{total !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Bar */}
      <div className="flex h-2 rounded-full overflow-hidden bg-[var(--surface-raised)]">
        {freeCount > 0 && (
          <motion.div
            className="bg-[var(--agree)] rounded-l-full"
            initial={{ width: 0 }}
            animate={{ width: `${freePct}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        )}
        {paywallCount > 0 && (
          <motion.div
            className="bg-[var(--accent)] rounded-r-full"
            initial={{ width: 0 }}
            animate={{ width: `${paywallPct}%` }}
            transition={{ duration: 0.5, ease: "easeOut", delay: 0.1 }}
          />
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[var(--agree)]" />
          <span className="text-mono text-[var(--text-muted)]">
            {freeCount} free
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[var(--accent)]" />
          <span className="text-mono text-[var(--text-muted)]">
            {paywallCount} paywalled
          </span>
        </div>
      </div>
    </div>
  );
}
