"use client";

import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/ui/BrandMark";

interface LoadingScreenProps {
  /** Short status line shown under the mark. */
  label?: string;
  /** Override the vertical fill (defaults to most of the viewport). */
  className?: string;
}

/**
 * LoadingScreen — calm, branded full-screen loader.
 *
 * The shared "load screen" used wherever we wait on data without a content-shaped
 * skeleton: route transitions (app/loading.tsx), the Capacitor story Suspense
 * fallback, and the onboarding profile check. A small wordmark over an
 * indeterminate amber scan bar. Honours prefers-reduced-motion.
 */
export function LoadingScreen({ label = "Loading", className }: LoadingScreenProps) {
  const reduce = useReducedMotion();

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className={cn(
        "flex flex-col items-center justify-center text-center px-[var(--space-lg)]",
        "min-h-[70vh]",
        className
      )}
    >
      <Logo markSize={22} textClassName="text-[22px]" className="mb-[var(--space-lg)]" />

      {/* Indeterminate amber scan bar */}
      <div className="relative h-[2px] w-32 overflow-hidden rounded-[var(--radius-full)] bg-[var(--surface-raised)]">
        {reduce ? (
          <div className="absolute inset-y-0 left-0 w-1/2 bg-[var(--accent)]" />
        ) : (
          <motion.div
            className="absolute inset-y-0 w-1/2 bg-[var(--accent)] rounded-[var(--radius-full)]"
            initial={{ x: "-110%" }}
            animate={{ x: "210%" }}
            transition={{
              duration: 1.1,
              ease: [0.16, 1, 0.3, 1],
              repeat: Infinity,
              repeatDelay: 0.15,
            }}
          />
        )}
      </div>

      <p className="text-mono uppercase text-[var(--text-muted)] mt-[var(--space-md)]">
        {label}
      </p>
    </div>
  );
}
