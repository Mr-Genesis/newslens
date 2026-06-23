import { cn } from "@/lib/utils";

interface ConfidenceScoreProps {
  sourceCount: number;
  coherence: number;
  className?: string;
}

/** Plain-language trust signal: sources + colour-coded agreement %.
 *  See docs/content/COPY-GUIDELINES.md §4. "coherence" is never shown to users. */
function agreement(coherence: number): { pct: number; color: string } {
  const pct = Math.round(coherence * 100);
  if (coherence >= 0.8) return { pct, color: "var(--agree)" };
  if (coherence >= 0.6) return { pct, color: "var(--warning)" };
  return { pct, color: "var(--text-muted)" };
}

export function ConfidenceScore({
  sourceCount,
  coherence,
  className,
}: ConfidenceScoreProps) {
  const { pct, color } = agreement(coherence);

  return (
    <span
      className={cn("text-mono inline-flex items-center gap-1.5", className)}
    >
      <span className="text-[var(--text-secondary)]">
        {sourceCount} {sourceCount === 1 ? "source" : "sources"}
      </span>
      <span className="text-[var(--text-ghost)]">&middot;</span>
      <span className="inline-flex items-center gap-1" style={{ color }}>
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: color }}
        />
        {pct}% agreement
      </span>
    </span>
  );
}
