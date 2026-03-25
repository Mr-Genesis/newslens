import { cn } from "@/lib/utils";

interface AISummaryBoxProps {
  summary: string | null;
  coherence?: number;
  className?: string;
}

export function AISummaryBox({ summary, coherence, className }: AISummaryBoxProps) {
  const isLow = coherence !== undefined && coherence < 0.6;

  return (
    <div
      className={cn(
        "rounded-[var(--radius-md)] bg-[var(--ai-summary-bg)] border-l-[3px] border-[var(--ai-summary-border)] p-4",
        className
      )}
    >
      <span className="text-mono text-[var(--ai-summary-label)] uppercase tracking-widest">
        AI Summary
      </span>

      {summary ? (
        <p
          className={cn(
            "text-small text-[var(--text-secondary)] mt-2",
            isLow && "tracking-[0.5px]"
          )}
        >
          {summary}
        </p>
      ) : (
        <p className="text-small text-[var(--text-muted)] mt-2 italic">
          AI analysis unavailable
        </p>
      )}

      <p className="text-mono text-[var(--ai-summary-disclaimer)] mt-3 text-[10px]">
        AI-generated summary &middot; may contain errors &middot; verify with sources below
      </p>
    </div>
  );
}
