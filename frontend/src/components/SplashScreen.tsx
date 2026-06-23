"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { BrandMark } from "@/components/ui/BrandMark";

/**
 * SplashScreen — branded app-open reveal.
 *
 * Mounted once in the root layout. Shows a full-viewport "NewsLens" wordmark on
 * cold start, then fades out and hands off to the app. Gated by sessionStorage
 * so it appears once per app session (a fresh launch), not on every in-app
 * navigation or re-render. Honours prefers-reduced-motion.
 */
const SEEN_KEY = "newslens-splash-seen";

export function SplashScreen() {
  const reduce = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  const [show, setShow] = useState(false);

  useEffect(() => {
    setMounted(true);
    let seen = false;
    try {
      seen = sessionStorage.getItem(SEEN_KEY) === "1";
    } catch {
      /* sessionStorage unavailable (private mode / SSR) — just show it */
    }
    if (seen) return;

    setShow(true);
    const hold = reduce ? 650 : 1500;
    const t = setTimeout(() => {
      setShow(false);
      try {
        sessionStorage.setItem(SEEN_KEY, "1");
      } catch {
        /* no-op */
      }
    }, hold);
    return () => clearTimeout(t);
  }, [reduce]);

  // Avoid hydration mismatch — render nothing on the server / first paint.
  if (!mounted) return null;

  // Timing helper: collapse all motion when the user prefers reduced motion.
  const t = (duration: number, delay = 0) =>
    reduce ? { duration: 0 } : { duration, delay, ease: [0.16, 1, 0.3, 1] as const };

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key="splash"
          role="status"
          aria-label="NewsLens is starting"
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-[var(--bg)] px-[var(--space-lg)]"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: reduce ? 0 : 0.45, ease: "easeIn" } }}
        >
          {/* Kicker — classified-brief framing */}
          <motion.p
            className="text-mono uppercase text-[var(--text-ghost)] mb-[var(--space-lg)]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={t(0.4, 0.05)}
          >
            Daily Intelligence Brief
          </motion.p>

          {/* Mark */}
          <motion.div
            className="text-[var(--text-primary)] mb-[var(--space-lg)]"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={t(0.5, 0.1)}
          >
            <BrandMark size={76} />
          </motion.div>

          {/* Wordmark */}
          <motion.div
            className="flex items-baseline"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={t(0.55, 0.12)}
          >
            <span className="text-[44px] sm:text-[56px] leading-none font-semibold tracking-[-0.02em] text-[var(--text-primary)] font-[family-name:var(--font-fraunces)]">
              News
            </span>
            <span className="text-[44px] sm:text-[56px] leading-none font-semibold tracking-[-0.02em] text-[var(--accent)] font-[family-name:var(--font-fraunces)]">
              Lens
            </span>
          </motion.div>

          {/* Amber underline — the single accent, "earned" as it draws in */}
          <motion.div
            className="h-[2px] w-16 bg-[var(--accent)] mt-[var(--space-md)] origin-left"
            initial={{ scaleX: 0, opacity: 0.6 }}
            animate={{ scaleX: 1, opacity: 1 }}
            transition={t(0.5, 0.4)}
          />

          {/* Tagline */}
          <motion.p
            className="text-small text-[var(--text-muted)] mt-[var(--space-lg)]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={t(0.4, 0.6)}
          >
            Breadth, not bubbles.
          </motion.p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
