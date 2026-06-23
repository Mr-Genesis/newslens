"use client";

import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

const THRESHOLD = 70;

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

  function onTouchStart(e: React.TouchEvent) {
    startY.current =
      window.scrollY <= 0 && !refreshing ? e.touches[0].clientY : null;
  }
  function onTouchMove(e: React.TouchEvent) {
    if (startY.current === null) return;
    const dy = e.touches[0].clientY - startY.current;
    if (dy > 0) setPull(Math.min(dy * 0.5, 90));
  }
  async function onTouchEnd() {
    if (startY.current === null) return;
    if (pull >= THRESHOLD) {
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
        transition={{ duration: refreshing ? 0.2 : 0 }}
        className="flex items-end justify-center overflow-hidden"
        aria-hidden="true"
      >
        <div
          className={cn(
            "mb-2 w-5 h-5 rounded-full border-2 border-[var(--accent)] border-t-transparent",
            refreshing && "animate-spin"
          )}
          style={{ opacity: pull > 10 || refreshing ? 1 : 0 }}
        />
      </motion.div>
      {children}
    </div>
  );
}
