import { Badge } from "@/components/ui/Badge";

/**
 * Phase 2 · #78 — provenance badges for the gated source tiers.
 *   research → RESEARCH   ·   expert → EXPERT · <author> · <score>   ·   preprint → PREPRINT · not peer-reviewed
 * A plain news source (or an unknown/NULL tier) renders nothing, so news cards are visually unchanged.
 */
interface SourceTierBadgeProps {
  sourceType?: string | null;
  authorName?: string | null;
  credibilityScore?: number | null;
  isPreprint?: boolean;
  size?: "sm" | "md";
  className?: string;
}

export function SourceTierBadge({
  sourceType,
  authorName,
  credibilityScore,
  isPreprint,
  size = "sm",
  className,
}: SourceTierBadgeProps) {
  const isResearch = sourceType === "research";
  const isExpert = sourceType === "expert";
  if (!isResearch && !isExpert) return null;

  // Author + score ride alongside the uppercase chip as normal-case mono text (the Badge itself
  // upper-cases, which would mangle a name like "Ben Thompson").
  const meta = [authorName, credibilityScore != null ? String(credibilityScore) : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <span className={`inline-flex items-center gap-1.5 ${className ?? ""}`}>
      {isResearch && (
        <Badge variant="signal" size={size}>
          RESEARCH
        </Badge>
      )}
      {isExpert && (
        <>
          <Badge variant="accent" size={size}>
            EXPERT
          </Badge>
          {meta && (
            <span className="font-[family-name:var(--font-jetbrains-mono)] text-[11px] text-[var(--text-muted)]">
              {meta}
            </span>
          )}
        </>
      )}
      {isPreprint && (
        <span className="inline-flex items-center gap-1.5">
          <Badge variant="outline" size={size}>
            PREPRINT
          </Badge>
          <span className="font-[family-name:var(--font-jetbrains-mono)] text-[10px] text-[var(--text-ghost)]">
            not peer-reviewed
          </span>
        </span>
      )}
    </span>
  );
}
