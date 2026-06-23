import { cn } from "@/lib/utils";

interface ConfidenceScoreProps {
  sourceCount: number;
  coherence: number;
  className?: string;
}

/** Plain-language trust signal (v2): "N sources · NN% agreement ●●●●".
 *  Colour-coded by tier; "coherence" is never shown to users.
 *  See docs/content/COPY-GUIDELINES.md §4. */
function tier(coherence: number): { pct: number; color: string; filled: number } {
  const pct = Math.round(coherence * 100);
  const filled = Math.max(1, Math.min(4, Math.round(coherence * 4)));
  if (coherence >= 0.8) return { pct, color: "var(--agree)", filled };
  if (coherence >= 0.6) return { pct, color: "var(--warning)", filled };
  return { pct, color: "var(--text-muted)", filled };
}

function Dots({ filled, color }: { filled: number; color: string }) {
  return (
    <span className="inline-flex items-center gap-[2px]" aria-hidden="true">
      {Array.from({ length: 4 }, (_, i) => (
        <span
          key={i}
          className="inline-block w-1 h-1 rounded-full"
          style={{
            backgroundColor: i < filled ? color : "var(--text-ghost)",
            opacity: i < filled ? 1 : 0.4,
          }}
        />
      ))}
    </span>
  );
}

export function ConfidenceScore({
  sourceCount,
  coherence,
  className,
}: ConfidenceScoreProps) {
  const { pct, color, filled } = tier(coherence);

  return (
    <span className={cn("text-mono inline-flex items-center gap-1.5", className)}>
      <span className="text-[var(--text-secondary)]">
        {sourceCount} {sourceCount === 1 ? "source" : "sources"}
      </span>
      <span className="text-[var(--text-ghost)]">&middot;</span>
      <span className="inline-flex items-center gap-1.5" style={{ color }}>
        <span>{pct}% agreement</span>
        <Dots filled={filled} color={color} />
      </span>
    </span>
  );
}
