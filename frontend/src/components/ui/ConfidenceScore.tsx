import { cn } from "@/lib/utils";

interface ConfidenceScoreProps {
  sourceCount: number;
  coherence: number;
  className?: string;
}

export function ConfidenceScore({
  sourceCount,
  coherence,
  className,
}: ConfidenceScoreProps) {
  const isLow = coherence < 0.6;

  return (
    <span className={cn("text-mono inline-flex items-center gap-1", className)}>
      <span className="text-[var(--accent)]">src:{sourceCount}</span>
      <span className="text-[var(--text-ghost)]">&middot;</span>
      <span
        className={cn(
          "text-[var(--text-ghost)]",
          isLow && "text-[var(--warning)]"
        )}
      >
        coh:{coherence.toFixed(2)}
      </span>
      {isLow && (
        <span className="text-[var(--warning)] text-[9px]" title="Low confidence">
          !
        </span>
      )}
    </span>
  );
}
