import { cn } from "@/lib/utils";

interface ConfidenceScoreProps {
  sourceCount: number;
  coherence: number;
  className?: string;
}

function getConfidenceLabel(coherence: number): {
  label: string;
  filled: number;
} {
  if (coherence >= 0.8) return { label: "High confidence", filled: 3 };
  if (coherence >= 0.6) return { label: "Moderate", filled: 2 };
  return { label: "Low confidence", filled: 1 };
}

function ConfidenceDots({ filled }: { filled: number }) {
  const total = 4;
  return (
    <span className="inline-flex items-center gap-[2px]">
      {Array.from({ length: total }, (_, i) => (
        <svg
          key={i}
          width="6"
          height="6"
          viewBox="0 0 6 6"
          className="inline-block"
        >
          <circle
            cx="3"
            cy="3"
            r="2.5"
            fill={
              i < filled
                ? "currentColor"
                : "var(--text-ghost)"
            }
            opacity={i < filled ? 1 : 0.3}
          />
        </svg>
      ))}
    </span>
  );
}

export function ConfidenceScore({
  sourceCount,
  coherence,
  className,
}: ConfidenceScoreProps) {
  const isLow = coherence < 0.6;
  const { label, filled } = getConfidenceLabel(coherence);

  return (
    <span
      className={cn("text-mono inline-flex items-center gap-1.5", className)}
    >
      <span className="text-[var(--accent)]">
        {sourceCount} {sourceCount === 1 ? "source" : "sources"}
      </span>
      <span className="text-[var(--text-ghost)]">&middot;</span>
      <span
        className={cn(
          "inline-flex items-center gap-1",
          isLow ? "text-[var(--warning)]" : "text-[var(--text-muted)]"
        )}
      >
        {label}
        <ConfidenceDots filled={filled} />
      </span>
    </span>
  );
}
