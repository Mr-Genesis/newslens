"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Button } from "@/components/ui/Button";
import { BrandMark } from "@/components/ui/BrandMark";
import { AnimatedMark } from "@/components/SplashScreen";

interface LaunchScreenProps {
  /** Re-check whether the briefing is ready. */
  onRetry: () => void;
  /** True while a re-check is in flight. */
  refreshing?: boolean;
}

/**
 * LaunchScreen — first-run / cold-start experience.
 *
 * Shown on the Today screen when there are no stories yet: a fresh install warms
 * up the feed (gathering sources, grouping stories, writing summaries) over a
 * couple of minutes. Branded, with a cycling step indicator so the wait reads as
 * progress rather than a dead screen. The Today page polls in the background;
 * "Check now" lets an impatient reader force a re-check.
 */
const STEPS = [
  "Gathering reports from across the web",
  "Grouping related stories together",
  "Writing plain-language summaries",
] as const;

export function LaunchScreen({ onRetry, refreshing = false }: LaunchScreenProps) {
  const reduce = useReducedMotion();
  const [step, setStep] = useState(0);

  // Cycle the step label so the screen feels alive during the wait.
  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => {
      setStep((s) => (s + 1) % STEPS.length);
    }, 2200);
    return () => clearInterval(id);
  }, [reduce]);

  return (
    <div className="flex flex-col items-center justify-center text-center min-h-[70vh] px-[var(--space-lg)]">
      {/* The designed loader — the mark ANIMATES while the news resolves (kit loop),
          not a static wordmark over skeletons. */}
      <div className="mb-[var(--space-md)]">
        {reduce ? <div className="text-[var(--text-primary)]"><BrandMark size={120} /></div> : <AnimatedMark size={120} loop />}
      </div>
      <div className="flex items-baseline mb-[var(--space-lg)]">
        <span className="text-[28px] leading-none font-semibold tracking-[-0.02em] text-[var(--text-primary)] font-[family-name:var(--font-fraunces)]">
          News
        </span>
        <span className="text-[28px] leading-none font-semibold tracking-[-0.02em] text-[var(--accent)] font-[family-name:var(--font-fraunces)]">
          Lens
        </span>
      </div>

      <h1 className="text-title text-[var(--text-primary)]">
        Preparing your first briefing
      </h1>
      <p className="text-small text-[var(--text-muted)] mt-2 max-w-[300px]">
        We&apos;re reading the news so you don&apos;t have to. This usually takes a
        couple of minutes the first time.
      </p>

      {/* Indeterminate progress track */}
      <div className="relative mt-[var(--space-xl)] h-[3px] w-48 overflow-hidden rounded-[var(--radius-full)] bg-[var(--surface-raised)]">
        {reduce ? (
          <div className="absolute inset-y-0 left-0 w-1/3 bg-[var(--accent)]" />
        ) : (
          <motion.div
            className="absolute inset-y-0 w-1/3 bg-[var(--accent)] rounded-[var(--radius-full)]"
            initial={{ x: "-110%" }}
            animate={{ x: "330%" }}
            transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], repeat: Infinity }}
          />
        )}
      </div>

      {/* Cycling step label */}
      <div className="h-5 mt-[var(--space-lg)] flex items-center">
        <motion.p
          key={reduce ? "static" : step}
          className="text-mono uppercase text-[var(--text-secondary)]"
          initial={reduce ? false : { opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
        >
          {reduce ? STEPS[0] : STEPS[step]}
        </motion.p>
      </div>

      <div className="mt-[var(--space-xl)]">
        <Button variant="secondary" size="md" onClick={onRetry} loading={refreshing}>
          Check now
        </Button>
      </div>

      <p className="text-mono text-[var(--text-ghost)] mt-[var(--space-lg)]">
        You can close the app — we&apos;ll keep it ready for you.
      </p>
    </div>
  );
}
