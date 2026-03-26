"use client";

import { cn } from "@/lib/utils";
import { motion, type HTMLMotionProps } from "framer-motion";
import { forwardRef } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends Omit<HTMLMotionProps<"button">, "ref"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--accent)] text-[var(--gray-950)] font-semibold hover:brightness-110",
  secondary:
    "bg-[var(--surface-raised)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
  ghost:
    "bg-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--surface-raised)]",
  danger:
    "bg-[var(--dismiss-muted)] text-[var(--dismiss)] hover:brightness-110",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-[13px] rounded-[var(--radius-md)] gap-1.5",
  md: "h-11 px-4 text-[14px] rounded-[var(--radius-md)] gap-2",
  lg: "h-12 px-5 text-[15px] rounded-[var(--radius-lg)] gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "primary",
      size = "md",
      fullWidth = false,
      loading = false,
      leftIcon,
      rightIcon,
      children,
      className,
      disabled,
      ...props
    },
    ref
  ) {
    return (
      <motion.button
        ref={ref}
        whileTap={{ scale: 0.97 }}
        whileHover={{ scale: 1.02 }}
        transition={{ duration: 0.15 }}
        className={cn(
          "inline-flex items-center justify-center font-medium transition-colors duration-[var(--duration-short)]",
          "disabled:opacity-40 disabled:pointer-events-none",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
          variantStyles[variant],
          sizeStyles[size],
          fullWidth && "w-full",
          className
        )}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <span className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          <>
            {leftIcon && <span className="shrink-0">{leftIcon}</span>}
            {children}
            {rightIcon && <span className="shrink-0">{rightIcon}</span>}
          </>
        )}
      </motion.button>
    );
  }
);
