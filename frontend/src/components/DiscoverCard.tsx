"use client";

import { motion, useMotionValue, useTransform, type PanInfo } from "framer-motion";
import { useCallback } from "react";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { cn } from "@/lib/utils";
import type { DiscoverCard as DiscoverCardType } from "@/lib/api";

interface DiscoverCardProps {
  card: DiscoverCardType;
  onSwipe: (direction: "right" | "left" | "up") => void;
  isTop: boolean;
  stackIndex: number; // 0 = top, 1 = middle, 2 = back
}

const COMMIT_THRESHOLD_X = 120; // px
const COMMIT_THRESHOLD_Y = -100; // px (negative = up)
const MAX_ROTATION = 8; // degrees

export function DiscoverCard({ card, onSwipe, isTop, stackIndex }: DiscoverCardProps) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  // Rotation based on horizontal drag
  const rotate = useTransform(x, [-300, 0, 300], [-MAX_ROTATION, 0, MAX_ROTATION]);

  // Edge glow opacity based on drag distance
  const glowRightOpacity = useTransform(x, [0, COMMIT_THRESHOLD_X], [0, 0.8]);
  const glowLeftOpacity = useTransform(x, [-COMMIT_THRESHOLD_X, 0], [0.8, 0]);
  const glowUpOpacity = useTransform(y, [COMMIT_THRESHOLD_Y, 0], [0.8, 0]);

  // Stack positioning
  const scale = 1 - stackIndex * 0.03;
  const translateY = stackIndex * 8;
  const opacity = 1 - stackIndex * 0.35;

  const handleDragEnd = useCallback(
    (_: unknown, info: PanInfo) => {
      const { offset, velocity } = info;

      // Check swipe-up first (strongest signal)
      if (offset.y < COMMIT_THRESHOLD_Y || velocity.y < -500) {
        onSwipe("up");
        return;
      }

      // Swipe right
      if (offset.x > COMMIT_THRESHOLD_X || velocity.x > 500) {
        onSwipe("right");
        return;
      }

      // Swipe left
      if (offset.x < -COMMIT_THRESHOLD_X || velocity.x < -500) {
        onSwipe("left");
        return;
      }

      // Below threshold — snap back (handled by dragSnapToOrigin)
    },
    [onSwipe]
  );

  return (
    <motion.div
      className={cn(
        "absolute inset-x-0 rounded-[var(--radius-md)] bg-[var(--swipe-card-bg)] overflow-hidden",
        isTop ? "cursor-grab active:cursor-grabbing" : "pointer-events-none"
      )}
      style={{
        x: isTop ? x : 0,
        y: isTop ? y : translateY,
        rotate: isTop ? rotate : 0,
        scale,
        opacity,
        zIndex: 22 - stackIndex,
      }}
      drag={isTop}
      dragConstraints={{ left: 0, right: 0, top: 0, bottom: 0 }}
      dragSnapToOrigin
      dragElastic={0.7}
      onDragEnd={isTop ? handleDragEnd : undefined}
      whileDrag={{ boxShadow: "var(--shadow-lg)" }}
      transition={{
        type: "spring",
        stiffness: 300,
        damping: 25,
      }}
    >
      {/* Edge glow overlays */}
      {isTop && (
        <>
          <motion.div
            className="absolute inset-0 pointer-events-none rounded-[var(--radius-md)]"
            style={{
              opacity: glowRightOpacity,
              boxShadow: "inset -4px 0 20px var(--swipe-glow-right)",
            }}
          />
          <motion.div
            className="absolute inset-0 pointer-events-none rounded-[var(--radius-md)]"
            style={{
              opacity: glowLeftOpacity,
              boxShadow: "inset 4px 0 20px var(--swipe-glow-left)",
            }}
          />
          <motion.div
            className="absolute inset-0 pointer-events-none rounded-[var(--radius-md)]"
            style={{
              opacity: glowUpOpacity,
              boxShadow: "inset 0 4px 20px var(--swipe-glow-up)",
            }}
          />
        </>
      )}

      {/* Card content */}
      <div className="p-6 flex flex-col h-[360px]">
        {/* Topic badge */}
        <div className="flex justify-end">
          <Badge variant="topic">{card.topic_name}</Badge>
        </div>

        {/* Tension line */}
        <h2 className="text-title text-[var(--text-primary)] mt-3 flex-shrink-0">
          {card.tension_line || card.title}
        </h2>

        {/* Facts */}
        <ul className="mt-4 space-y-2 flex-1 overflow-hidden">
          {card.facts.map((fact, i) => (
            <li
              key={i}
              className="text-small text-[var(--text-secondary)] flex items-start gap-2"
            >
              <span className="text-[var(--text-ghost)] shrink-0 mt-[2px]">&bull;</span>
              <span className="line-clamp-2">{fact}</span>
            </li>
          ))}
        </ul>

        {/* Footer */}
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-[var(--border-subtle)]">
          <span className="text-mono text-[var(--text-ghost)] truncate">
            {card.sources.join(" · ")}
          </span>
          <ConfidenceScore
            sourceCount={card.sources.length}
            coherence={card.coherence}
          />
        </div>
      </div>
    </motion.div>
  );
}
