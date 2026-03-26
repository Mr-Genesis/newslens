"use client";

import { cn } from "@/lib/utils";
import { motion, type HTMLMotionProps } from "framer-motion";
import { forwardRef } from "react";

type IconButtonVariant = "default" | "filled" | "accent";

interface IconButtonProps extends Omit<HTMLMotionProps<"button">, "ref"> {
  variant?: IconButtonVariant;
  size?: "sm" | "md" | "lg";
  label: string;
}

const variantStyles: Record<IconButtonVariant, string> = {
  default:
    "text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--surface-raised)]",
  filled:
    "bg-[var(--surface-raised)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
  accent:
    "text-[var(--accent)] hover:bg-[var(--accent-subtle)]",
};

const sizeStyles: Record<string, string> = {
  sm: "h-8 w-8",
  md: "h-10 w-10",
  lg: "h-12 w-12",
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    { variant = "default", size = "md", label, className, children, ...props },
    ref
  ) {
    return (
      <motion.button
        ref={ref}
        whileTap={{ scale: 0.9 }}
        transition={{ duration: 0.1 }}
        aria-label={label}
        className={cn(
          "inline-flex items-center justify-center rounded-full transition-colors duration-[var(--duration-short)]",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
          "disabled:opacity-40 disabled:pointer-events-none",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {children}
      </motion.button>
    );
  }
);
