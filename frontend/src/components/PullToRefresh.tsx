"use client";

import { useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { pullOffset, pullTriggersRefresh } from "@/lib/pull";

/** Touch pull-to-refresh. Activates only at scroll-top on touch devices;
 *  desktop keeps the in-page refresh button. */
export function PullToRefresh({
  onRefresh,
  children,
}: {
  onRefresh: () => Promise<void> | void;
  children: React.ReactNode;
}) {
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef<number | null>(null);
  const reduce = useReducedMotion();

  function onTouchStart(e: React.TouchEvent) {
    startY.current =
      window.scrollY <= 0 && !refreshing ? e.touches[0].clientY : null;
  }
  function onTouchMove(e: React.TouchEvent) {
    if (startY.current === null) return;
    const dy = e.touches[0].clientY - startY.current;
    if (dy > 0) setPull(pullOffset(dy)); // #99: spec rubber-band (×0.4, cap 80)
  }
  async function onTouchEnd() {
    if (startY.current === null) return;
    if (pullTriggersRefresh(pull)) {
      setRefreshing(true);
      try {
        await onRefresh();
      } finally {
        setRefreshing(false);
      }
    }
    setPull(0);
    startY.current = null;
  }

  return (
    <div onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
      <motion.div
        animate={{ height: refreshing ? 40 : pull }}
        transition={{ duration: reduce ? 0 : refreshing ? 0.2 : 0 }}  // #99: no spring when reduced-motion
        className="flex items-end justify-center overflow-hidden"
        aria-hidden="true"
      >
        <div
          className={cn(
            "mb-2 w-5 h-5 rounded-full border-2 border-[var(--accent)] border-t-transparent",
            refreshing && !reduce && "animate-spin"
          )}
          style={{ opacity: pull > 10 || refreshing ? 1 : 0 }}
        />
      </motion.div>
      {children}
    </div>
  );
}
