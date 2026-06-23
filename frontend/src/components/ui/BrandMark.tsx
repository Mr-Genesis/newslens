import { cn } from "@/lib/utils";

/**
 * NewsLens mark — square brackets framing three left-aligned "story lines" and a
 * centered amber "lens" dot. Geometry + colors come straight from the official
 * brand source (NewsLens Brand Identity → Mark.dc.html, viewBox 0 0 100 100):
 * brackets + the bright middle line use the "bar" color (#E4E4E7 → currentColor
 * here so the lockup adapts to theme), the top/bottom lines are the dim "ghost"
 * (#3F3F46 → --text-ghost), and the lens is the amber accent. Centered to origin.
 */
export function BrandMark({
  size = 24,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="-50 -50 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-hidden
    >
      {/* Brackets */}
      <path d="M-15 -24 H-28 V24 H-15" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15 -24 H28 V24 H15" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Story lines — bright middle (bar), dim top/bottom (ghost) */}
      <line x1="-17" y1="-9" x2="-6" y2="-9" stroke="var(--text-ghost)" strokeWidth="4" strokeLinecap="round" />
      <line x1="-21" y1="0" x2="-7" y2="0" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <line x1="-17" y1="9" x2="-6" y2="9" stroke="var(--text-ghost)" strokeWidth="4" strokeLinecap="round" />
      {/* Lens dot (centered, on top of the lines) */}
      <circle cx="0" cy="0" r="7" fill="var(--accent)" />
    </svg>
  );
}

/**
 * Horizontal logo lockup: mark + "NewsLens" wordmark. Brackets + "News" inherit
 * text-primary; the lens dot + "Lens" carry the amber accent.
 */
export function Logo({
  markSize = 22,
  textClassName = "text-[20px]",
  className,
}: {
  markSize?: number;
  textClassName?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 text-[var(--text-primary)]",
        className
      )}
    >
      <BrandMark size={markSize} />
      <span className="flex items-baseline">
        <span
          className={cn(
            "font-semibold tracking-[-0.01em] font-[family-name:var(--font-fraunces)]",
            textClassName
          )}
        >
          News
        </span>
        <span
          className={cn(
            "font-semibold tracking-[-0.01em] text-[var(--accent)] font-[family-name:var(--font-fraunces)]",
            textClassName
          )}
        >
          Lens
        </span>
      </span>
    </span>
  );
}
