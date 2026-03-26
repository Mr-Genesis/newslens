"use client";

import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

interface ChipProps {
  selected?: boolean;
  onClick?: () => void;
  color?: string;
  children: React.ReactNode;
  className?: string;
}

export function Chip({
  selected = false,
  onClick,
  color,
  children,
  className,
}: ChipProps) {
  return (
    <motion.button
      whileTap={{ scale: 0.95 }}
      transition={{ duration: 0.1 }}
      onClick={onClick}
      className={cn(
        "inline-flex items-center px-3 py-1.5 rounded-full text-[13px] font-medium whitespace-nowrap",
        "transition-colors duration-[var(--duration-short)]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
        selected
          ? "bg-[var(--accent)] text-[var(--gray-950)]"
          : "bg-transparent border border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--text-muted)] hover:text-[var(--text-primary)]",
        className
      )}
      style={
        selected && color
          ? { backgroundColor: color, color: "var(--gray-950)" }
          : undefined
      }
    >
      {children}
    </motion.button>
  );
}
