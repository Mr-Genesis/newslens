import { cn } from "@/lib/utils";

type BadgeVariant = "free" | "paywall" | "topic" | "accent" | "signal";

const variants: Record<BadgeVariant, string> = {
  free: "bg-[var(--agree-muted)] text-[var(--agree)]",
  paywall: "bg-[var(--dismiss-muted)] text-[var(--dismiss)]",
  topic: "bg-[var(--drill-muted)] text-[var(--drill)]",
  accent: "bg-[var(--accent-subtle)] text-[var(--accent)]",
  signal: "bg-[rgba(34,211,238,0.12)] text-[var(--signal)]",
};

interface BadgeProps {
  variant: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-[6px] py-[1px] rounded-[var(--radius-sm)] text-mono font-medium uppercase",
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
