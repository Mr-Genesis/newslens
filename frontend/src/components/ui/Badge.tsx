import { cn } from "@/lib/utils";

type BadgeVariant =
  | "free"
  | "paywall"
  | "topic"
  | "accent"
  | "signal"
  | "outline"
  | "dot";
type BadgeSize = "sm" | "md";

const variants: Record<Exclude<BadgeVariant, "dot">, string> = {
  free: "bg-[var(--agree-muted)] text-[var(--agree)]",
  paywall: "bg-[var(--dismiss-muted)] text-[var(--dismiss)]",
  topic: "bg-[var(--drill-muted)] text-[var(--drill)]",
  accent: "bg-[var(--accent-subtle)] text-[var(--accent)]",
  signal: "bg-[rgba(34,211,238,0.12)] text-[var(--signal)]",
  outline:
    "bg-transparent border border-[var(--border)] text-[var(--text-muted)]",
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: "px-[6px] py-[1px] text-[10px]",
  md: "px-2 py-0.5 text-[11px]",
};

interface BadgeProps {
  variant: BadgeVariant;
  size?: BadgeSize;
  color?: string;
  children?: React.ReactNode;
  className?: string;
}

export function Badge({
  variant,
  size = "sm",
  color,
  children,
  className,
}: BadgeProps) {
  if (variant === "dot") {
    return (
      <span
        className={cn("inline-block h-1.5 w-1.5 rounded-full", className)}
        style={{ backgroundColor: color || "var(--accent)" }}
      />
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[var(--radius-sm)] font-medium uppercase tracking-wide",
        "font-[family-name:var(--font-jetbrains-mono)]",
        variants[variant],
        sizeStyles[size],
        className
      )}
      style={color ? { backgroundColor: `${color}20`, color } : undefined}
    >
      {children}
    </span>
  );
}
