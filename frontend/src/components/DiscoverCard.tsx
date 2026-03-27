"use client";

import {
  motion,
  useMotionValue,
  useTransform,
  type PanInfo,
} from "framer-motion";
import { useCallback } from "react";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { cn } from "@/lib/utils";
import type { DiscoverCard as DiscoverCardType } from "@/lib/api";

interface DiscoverCardProps {
  card: DiscoverCardType;
  onSwipe: (direction: "right" | "left" | "up") => void;
  isTop: boolean;
  stackIndex: number;
}

const COMMIT_THRESHOLD_X = 120;
const COMMIT_THRESHOLD_Y = -100;
const MAX_ROTATION = 8;

const topicColorMap: Record<string, string> = {
  technology: "var(--topic-tech)",
  tech: "var(--topic-tech)",
  politics: "var(--topic-politics)",
  business: "var(--topic-business)",
  science: "var(--topic-science)",
  sports: "var(--topic-sports)",
  health: "var(--topic-health)",
  world: "var(--topic-world)",
};

function getTopicColor(topicName: string): string {
  const lower = topicName.toLowerCase();
  return topicColorMap[lower] || "var(--topic-default)";
}

export function DiscoverCard({
  card,
  onSwipe,
  isTop,
  stackIndex,
}: DiscoverCardProps) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const rotate = useTransform(
    x,
    [-300, 0, 300],
    [-MAX_ROTATION, 0, MAX_ROTATION]
  );

  const glowRightOpacity = useTransform(
    x,
    [0, COMMIT_THRESHOLD_X],
    [0, 0.8]
  );
  const glowLeftOpacity = useTransform(
    x,
    [-COMMIT_THRESHOLD_X, 0],
    [0.8, 0]
  );
  const glowUpOpacity = useTransform(y, [COMMIT_THRESHOLD_Y, 0], [0.8, 0]);

  const scale = 1 - stackIndex * 0.03;
  const translateY = stackIndex * 8;
  const opacity = 1 - stackIndex * 0.35;
  const topicColor = getTopicColor(card.topic_name);

  const handleDragEnd = useCallback(
    (_: unknown, info: PanInfo) => {
      const { offset, velocity } = info;

      if (offset.y < COMMIT_THRESHOLD_Y || velocity.y < -500) {
        onSwipe("up");
        return;
      }
      if (offset.x > COMMIT_THRESHOLD_X || velocity.x > 500) {
        onSwipe("right");
        return;
      }
      if (offset.x < -COMMIT_THRESHOLD_X || velocity.x < -500) {
        onSwipe("left");
        return;
      }
    },
    [onSwipe]
  );

  return (
    <motion.div
      className={cn(
        "absolute inset-x-0 rounded-[var(--radius-lg)] overflow-hidden",
        "bg-[var(--surface-card)] border border-[var(--glass-border)]",
        isTop ? "cursor-grab active:cursor-grabbing" : "pointer-events-none"
      )}
      style={{
        x: isTop ? x : 0,
        y: isTop ? y : translateY,
        rotate: isTop ? rotate : 0,
        scale,
        opacity,
        zIndex: 22 - stackIndex,
        borderTop: `2px solid ${topicColor}`,
      }}
      drag={isTop}
      dragConstraints={{ left: 0, right: 0, top: 0, bottom: 0 }}
      dragSnapToOrigin
      dragElastic={0.7}
      onDragEnd={isTop ? handleDragEnd : undefined}
      whileDrag={{ boxShadow: "var(--shadow-lg)" }}
      exit={{
        opacity: 0,
        scale: 0.9,
        transition: { duration: 0.2 },
      }}
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
            className="absolute inset-0 pointer-events-none rounded-[var(--radius-lg)]"
            style={{
              opacity: glowRightOpacity,
              boxShadow: "inset -4px 0 20px var(--swipe-glow-right)",
            }}
          />
          <motion.div
            className="absolute inset-0 pointer-events-none rounded-[var(--radius-lg)]"
            style={{
              opacity: glowLeftOpacity,
              boxShadow: "inset 4px 0 20px var(--swipe-glow-left)",
            }}
          />
          <motion.div
            className="absolute inset-0 pointer-events-none rounded-[var(--radius-lg)]"
            style={{
              opacity: glowUpOpacity,
              boxShadow: "inset 0 4px 20px var(--swipe-glow-up)",
            }}
          />
        </>
      )}

      {/* Card content */}
      <div
        className={cn("p-4 flex flex-col", !isTop && "invisible")}
        style={{ height: "min(340px, calc(100dvh - 260px))" }}
      >
        {/* Topic badge — top left */}
        <div className="flex items-center gap-2">
          <Badge variant="topic" size="md" color={topicColor}>
            {card.topic_name}
          </Badge>
        </div>

        {/* Tension line — italic emphasis (the ONE place italic lives) */}
        <h2 className="text-title text-emphasis text-[var(--text-primary)] mt-4 flex-shrink-0">
          {card.tension_line || card.title}
        </h2>

        {/* Facts */}
        <ul className="mt-4 space-y-2.5 flex-1 overflow-hidden">
          {card.facts.map((fact, i) => (
            <li
              key={i}
              className="text-small text-[var(--text-secondary)] flex items-start gap-2.5"
            >
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0 mt-[7px]"
                style={{ backgroundColor: topicColor }}
              />
              <span className="line-clamp-2">{fact}</span>
            </li>
          ))}
        </ul>

        {/* Footer */}
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-[var(--glass-border)]">
          <span className="text-mono text-[var(--text-ghost)] truncate max-w-[60%]">
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
