import { cn } from "@/lib/utils";

/**
 * NewsLens mark — square brackets framing three left-aligned "story lines" and a
 * centered amber "lens" dot. Geometry + colors are traced directly from the master
 * mark asset (NewsLens Mark.png): brackets #E4E4E7 (here currentColor so the lockup
 * adapts to theme), top/bottom lines #3F3F46, the brighter middle line #52525B, and
 * the lens in the amber accent.
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
      viewBox="-120 -120 240 240"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-hidden
    >
      {/* Brackets */}
      <path
        d="M-54 -77 H-89 V77 H-54"
        fill="none"
        stroke="currentColor"
        strokeWidth="15"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M54 -77 H89 V77 H54"
        fill="none"
        stroke="currentColor"
        strokeWidth="15"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Story lines (left-aligned; middle is brighter) */}
      <path d="M-55 -29 H-19" stroke="#3F3F46" strokeWidth="11" strokeLinecap="round" />
      <path d="M-68 0 H-29" stroke="#52525B" strokeWidth="11" strokeLinecap="round" />
      <path d="M-55 29 H-19" stroke="#3F3F46" strokeWidth="11" strokeLinecap="round" />
      {/* Lens dot (centered, on top of the lines) */}
      <circle cx="0" cy="0" r="21.5" fill="var(--accent)" />
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
