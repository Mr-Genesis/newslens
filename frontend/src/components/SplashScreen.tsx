"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Capacitor } from "@capacitor/core";
import { BrandMark } from "@/components/ui/BrandMark";

/**
 * SplashScreen — branded cold-start reveal, per the official Splash design.
 *
 * Shows the animated NewsLens mark (the brand GIF) over the wordmark with a
 * resolving progress bar, then fades out and hands off to the app. Mounted once
 * in the root layout and gated by sessionStorage so it appears once per app
 * session (a fresh launch). Reduced-motion users get the static mark instead of
 * the looping GIF.
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
    const hold = reduce ? 700 : 2200;
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

  // Native (Capacitor): hand off from the held native splash to the web app with
  // a controlled fade, once the WebView has painted this overlay. The native
  // splash is configured with launchAutoHide:false so it never flashes the bare
  // WebView before React mounts.
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    const raf = requestAnimationFrame(() => {
      import("@capacitor/splash-screen")
        .then(({ SplashScreen }) => SplashScreen.hide({ fadeOutDuration: 250 }))
        .catch(() => {});
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  // Avoid hydration mismatch — render nothing on the server / first paint.
  if (!mounted) return null;

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key="splash"
          role="status"
          aria-label="NewsLens is starting"
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-[34px] bg-[#0C0C0E] px-[var(--space-lg)]"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: reduce ? 0 : 0.45, ease: "easeIn" } }}
        >
          {/* Animated mark — the brand GIF (static mark under reduced motion) */}
          {reduce ? (
            <div className="text-[var(--text-primary)]">
              <BrandMark size={132} />
            </div>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src="/newslens-mark.gif"
              alt=""
              width={150}
              height={150}
              className="w-[150px] h-[150px] select-none"
              draggable={false}
            />
          )}

          {/* Wordmark */}
          <div className="flex items-baseline">
            <span className="text-[40px] sm:text-[48px] leading-none font-semibold tracking-[-0.02em] text-[var(--text-primary)] font-[family-name:var(--font-fraunces)]">
              News
            </span>
            <span className="text-[40px] sm:text-[48px] leading-none font-semibold tracking-[-0.02em] text-[var(--accent)] font-[family-name:var(--font-fraunces)]">
              Lens
            </span>
          </div>

          {/* Resolving progress + status label */}
          <div className="absolute bottom-[54px] left-0 right-0 flex flex-col items-center gap-3.5">
            <div className="w-[150px] h-[2px] rounded-full bg-[var(--border-subtle)] overflow-hidden">
              {reduce ? (
                <div className="w-1/3 h-full bg-[var(--text-primary)]" />
              ) : (
                <motion.div
                  className="w-[46px] h-full rounded-full bg-[var(--text-primary)]"
                  initial={{ x: -46 }}
                  animate={{ x: 150 }}
                  transition={{ duration: 1.5, ease: [0.65, 0, 0.35, 1], repeat: Infinity }}
                />
              )}
            </div>
            <p className="text-mono uppercase text-[var(--text-ghost)]">
              Assembling your briefing
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
