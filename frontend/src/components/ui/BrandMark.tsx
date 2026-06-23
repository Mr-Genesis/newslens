import { cn } from "@/lib/utils";

/**
 * NewsLens mark — square brackets framing three "story lines" that flow into the
 * amber "lens" dot. Brackets use currentColor (set the parent's text color); the
 * lines are a muted gray; the lens dot is the single amber accent and sits on top
 * of the lines. Geometry matches the master mark animation.
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
      viewBox="-320 -320 640 640"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-hidden
    >
      {/* Brackets */}
      <path
        d="M-180 -156 H-264 V156 H-180"
        fill="none"
        stroke="currentColor"
        strokeWidth="30"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M180 -156 H264 V156 H180"
        fill="none"
        stroke="currentColor"
        strokeWidth="30"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Story lines */}
      <g stroke="#52525B" strokeWidth="28" strokeLinecap="round">
        <path d="M-175 -60 H-42" />
        <path d="M-175 0 H18" />
        <path d="M-175 60 H-52" />
      </g>
      {/* Lens dot (on top of the lines) */}
      <circle cx="28" cy="0" r="62" fill="var(--accent)" />
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
