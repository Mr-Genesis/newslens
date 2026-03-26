"use client";

import { cn } from "@/lib/utils";
import { motion, type HTMLMotionProps } from "framer-motion";
import { forwardRef } from "react";

type CardVariant = "flat" | "raised" | "elevated" | "glass";

interface CardProps extends Omit<HTMLMotionProps<"div">, "ref"> {
  variant?: CardVariant;
  pressable?: boolean;
  topAccentColor?: string;
}

const variantStyles: Record<CardVariant, string> = {
  flat: "bg-[var(--surface)]",
  raised: "bg-[var(--surface-raised)] shadow-[var(--shadow-sm)]",
  elevated:
    "bg-[var(--surface-raised)] shadow-[var(--shadow-md)] border border-[var(--border-subtle)]",
  glass: "glass-light",
};

export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  {
    variant = "flat",
    pressable = false,
    topAccentColor,
    className,
    children,
    style,
    ...props
  },
  ref
) {
  return (
    <motion.div
      ref={ref}
      whileTap={pressable ? { scale: 0.98 } : undefined}
      transition={{ duration: 0.15 }}
      className={cn(
        "rounded-[var(--radius-lg)] overflow-hidden",
        variantStyles[variant],
        pressable && "cursor-pointer",
        className
      )}
      style={{
        ...style,
        ...(topAccentColor
          ? {
              borderTop: `2px solid ${topAccentColor}`,
            }
          : {}),
      }}
      {...props}
    >
      {children}
    </motion.div>
  );
});
