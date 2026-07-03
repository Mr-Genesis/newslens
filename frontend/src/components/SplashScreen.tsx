"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Capacitor } from "@capacitor/core";
import { BrandMark } from "@/components/ui/BrandMark";

/**
 * SplashScreen — branded cold-start reveal, per the official Splash design.
 *
 * Plays the OFFICIAL mark choreography (from the brand kit's "NewsLens Mark -
 * Animated" source: source ticks gather → editorial brackets close in while
 * drawing on → the amber story-dot pops with a resolution ring → wordmark
 * rises), then fades out and hands off to the app. Rendered as a native
 * one-shot SVG animation — NOT the looping GIF export, whose raster loop read
 * as "lines outside the brackets". Mounted once in the root layout and gated
 * by sessionStorage so it appears once per app session (a fresh launch).
 * Reduced-motion users get the static mark.
 */
const SEEN_KEY = "newslens-splash-seen";

/**
 * Official mark choreography (brand kit "NewsLens Mark - Animated"): ticks gather →
 * brackets close in while drawing on → the story-dot pops with a resolution ring.
 * Default = one-shot reveal (splash). `loop` = the kit's original 5.5s infinite cycle
 * (loaders — the "logo animates while news resolves" screen).
 */
export function AnimatedMark({ size = 150, loop = false }: { size?: number; loop?: boolean }) {
  const cls = loop ? "lp" : "os";
  return (
    <div style={{ width: size, height: size }}>
      <style>{`
        @keyframes nlBracketL{0%{stroke-dashoffset:74;opacity:0;transform:translateX(-7px)}22%{opacity:1}100%{stroke-dashoffset:0;opacity:1;transform:translateX(0)}}
        @keyframes nlBracketR{0%{stroke-dashoffset:74;opacity:0;transform:translateX(7px)}22%{opacity:1}100%{stroke-dashoffset:0;opacity:1;transform:translateX(0)}}
        @keyframes nlTickIn{0%{opacity:0}55%{opacity:var(--to)}100%{opacity:calc(var(--to)*0.32)}}
        @keyframes nlDotPop{0%,62%{transform:scale(0);opacity:0}78%{transform:scale(1.22);opacity:1}90%{transform:scale(1)}100%{transform:scale(1);opacity:1}}
        @keyframes nlRingOut{0%,64%{transform:scale(1);opacity:0}70%{transform:scale(1.12);opacity:.55}100%{transform:scale(3.4);opacity:0}}
        .os-bl{stroke-dasharray:74;transform-box:view-box;animation:nlBracketL .9s cubic-bezier(.5,.05,.18,1) .15s both}
        .os-br{stroke-dasharray:74;transform-box:view-box;animation:nlBracketR .9s cubic-bezier(.5,.05,.18,1) .15s both}
        .os-t{animation:nlTickIn 1.35s ease-in-out both}
        .os-dot{transform-box:fill-box;transform-origin:center;animation:nlDotPop 1.75s cubic-bezier(.34,1.56,.64,1) both}
        .os-ring{transform-box:fill-box;transform-origin:center;animation:nlRingOut 1.75s ease-out both}
        /* loop mode — kit's original infinite cycle (percentages from the standalone HTML) */
        @keyframes nlBracketLoopL{0%,7%{stroke-dashoffset:74;opacity:0;transform:translateX(-7px)}16%{opacity:1}38%{stroke-dashoffset:0;opacity:1;transform:translateX(0)}86%{stroke-dashoffset:0;opacity:1;transform:translateX(0)}100%{stroke-dashoffset:74;opacity:0;transform:translateX(-7px)}}
        @keyframes nlBracketLoopR{0%,7%{stroke-dashoffset:74;opacity:0;transform:translateX(7px)}16%{opacity:1}38%{stroke-dashoffset:0;opacity:1;transform:translateX(0)}86%{stroke-dashoffset:0;opacity:1;transform:translateX(0)}100%{stroke-dashoffset:74;opacity:0;transform:translateX(7px)}}
        @keyframes nlTickLoop{0%,4%{opacity:0}22%{opacity:var(--to)}40%{opacity:var(--to)}54%{opacity:calc(var(--to)*0.32)}86%{opacity:calc(var(--to)*0.32)}100%{opacity:0}}
        @keyframes nlDotLoop{0%,40%{transform:scale(0);opacity:0}50%{transform:scale(1.22);opacity:1}58%{transform:scale(1);opacity:1}86%{transform:scale(1);opacity:1}100%{transform:scale(0.55);opacity:0}}
        @keyframes nlRingLoop{0%,42%{transform:scale(1);opacity:0}46%{transform:scale(1.12);opacity:.55}64%{transform:scale(3.4);opacity:0}100%{transform:scale(3.4);opacity:0}}
        .lp-bl{stroke-dasharray:74;transform-box:view-box;animation:nlBracketLoopL 5.5s cubic-bezier(.5,.05,.18,1) infinite}
        .lp-br{stroke-dasharray:74;transform-box:view-box;animation:nlBracketLoopR 5.5s cubic-bezier(.5,.05,.18,1) infinite}
        .lp-t{animation:nlTickLoop 5.5s ease-in-out infinite}
        .lp-dot{transform-box:fill-box;transform-origin:center;animation:nlDotLoop 5.5s cubic-bezier(.34,1.56,.64,1) infinite}
        .lp-ring{transform-box:fill-box;transform-origin:center;animation:nlRingLoop 5.5s ease-out infinite}
      `}</style>
      <svg viewBox="0 0 100 100" style={{ display: "block", width: "100%", height: "100%", overflow: "visible" }}>
        {/* source ticks: faint reports waiting to be resolved — always INSIDE the brackets */}
        <line x1="33" y1="41" x2="44" y2="41" stroke="#3F3F46" strokeWidth="4" strokeLinecap="round" className={`${cls}-t`} style={{ ["--to" as string]: 0.85, animationDelay: "0.12s" }} />
        <line x1="29" y1="50" x2="43" y2="50" stroke="#A1A1AA" strokeWidth="4" strokeLinecap="round" className={`${cls}-t`} style={{ ["--to" as string]: 1, animationDelay: "0.05s" }} />
        <line x1="33" y1="59" x2="44" y2="59" stroke="#3F3F46" strokeWidth="4" strokeLinecap="round" className={`${cls}-t`} style={{ ["--to" as string]: 0.85, animationDelay: "0.19s" }} />
        {/* the resolution ring — expands once at the instant of focus */}
        <circle cx="50" cy="50" r="8" fill="none" stroke="#F97316" strokeWidth="1.4" className={`${cls}-ring`} />
        {/* editorial brackets closing in */}
        <path d="M35 26 H22 V74 H35" fill="none" stroke="#E4E4E7" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" className={`${cls}-bl`} />
        <path d="M65 26 H78 V74 H65" fill="none" stroke="#E4E4E7" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" className={`${cls}-br`} />
        {/* the single story, in focus */}
        <circle cx="50" cy="50" r="7" fill="#F97316" className={`${cls}-dot`} />
      </svg>
    </div>
  );
}

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
    const hold = reduce ? 700 : 2800; // let the full choreography land (ticks→brackets→dot→wordmark)
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
          {/* Animated mark — official kit choreography (static mark under reduced motion) */}
          {reduce ? (
            <div className="text-[var(--text-primary)]">
              <BrandMark size={132} />
            </div>
          ) : (
            <AnimatedMark size={150} />
          )}

          {/* Wordmark — resolves in beneath the mark once focus is found (kit nlWord timing) */}
          <motion.div
            className="flex items-baseline"
            initial={reduce ? false : { opacity: 0, y: 9 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: reduce ? 0 : 1.15, duration: 0.45, ease: "easeOut" }}
          >
            <span className="text-[40px] sm:text-[48px] leading-none font-semibold tracking-[-0.02em] text-[var(--text-primary)] font-[family-name:var(--font-fraunces)]">
              News
            </span>
            <span className="text-[40px] sm:text-[48px] leading-none font-semibold tracking-[-0.02em] text-[var(--accent)] font-[family-name:var(--font-fraunces)]">
              Lens
            </span>
          </motion.div>

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
