"use client";

import {
  motion,
  useMotionValue,
  useTransform,
  type PanInfo,
} from "framer-motion";
import { useCallback, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { SourceTierBadge } from "@/components/ui/SourceTierBadge";
import { cn } from "@/lib/utils";
import { addFollow, type DiscoverCard as DiscoverCardType } from "@/lib/api";

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
  return topicColorMap[topicName.toLowerCase()] || "var(--topic-default)";
}

function agreementColor(coherence: number): string {
  if (coherence >= 0.8) return "var(--agree)";
  if (coherence >= 0.6) return "var(--warning)";
  return "var(--text-muted)";
}

export function DiscoverCard({
  card,
  onSwipe,
  isTop,
  stackIndex,
}: DiscoverCardProps) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const rotate = useTransform(x, [-300, 0, 300], [-MAX_ROTATION, 0, MAX_ROTATION]);
  const glowRightOpacity = useTransform(x, [0, COMMIT_THRESHOLD_X], [0, 0.9]);
  const glowLeftOpacity = useTransform(x, [-COMMIT_THRESHOLD_X, 0], [0.9, 0]);
  const glowUpOpacity = useTransform(y, [COMMIT_THRESHOLD_Y, 0], [0.8, 0]);

  const scale = 1 - stackIndex * 0.03;
  const translateY = stackIndex * 8;
  const opacity = 1 - stackIndex * 0.35;
  const topicColor = getTopicColor(card.topic_name);
  const pct = Math.round(card.coherence * 100);
  const aColor = agreementColor(card.coherence);
  const filled = Math.max(1, Math.min(4, Math.round(card.coherence * 4)));

  const handleDragEnd = useCallback(
    (_: unknown, info: PanInfo) => {
      const { offset, velocity } = info;
      if (offset.y < COMMIT_THRESHOLD_Y || velocity.y < -500) return onSwipe("up");
      if (offset.x > COMMIT_THRESHOLD_X || velocity.x > 500) return onSwipe("right");
      if (offset.x < -COMMIT_THRESHOLD_X || velocity.x < -500) return onSwipe("left");
    },
    [onSwipe]
  );

  // #83: discover is the opt-in surface for gated tiers. A lightweight, optimistic follow (no
  // getFollows round-trip — 25 cards mount at once; addFollow is idempotent server-side).
  const [followed, setFollowed] = useState(false);
  const followSource = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      if (followed || card.source_id == null) return;
      setFollowed(true);
      try {
        await addFollow("source", String(card.source_id));
      } catch {
        setFollowed(false);
      }
    },
    [followed, card.source_id]
  );

  return (
    <motion.div
      className={cn(
        // inset-0: the card FILLS the stack container (page owns the height) — the old
        // inset-x-0 + own-height pair let the card overflow the container onto the buttons.
        "absolute inset-0 rounded-[var(--radius-lg)] overflow-hidden",
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
      exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
    >
      {/* Edge glow overlays */}
      {isTop && (
        <>
          <motion.div className="absolute inset-0 pointer-events-none rounded-[var(--radius-lg)]" style={{ opacity: glowRightOpacity, boxShadow: "inset -4px 0 20px var(--swipe-glow-right)" }} />
          <motion.div className="absolute inset-0 pointer-events-none rounded-[var(--radius-lg)]" style={{ opacity: glowLeftOpacity, boxShadow: "inset 4px 0 20px var(--swipe-glow-left)" }} />
          <motion.div className="absolute inset-0 pointer-events-none rounded-[var(--radius-lg)]" style={{ opacity: glowUpOpacity, boxShadow: "inset 0 4px 20px var(--swipe-glow-up)" }} />
          {/* Swipe stamps */}
          <motion.div style={{ opacity: glowRightOpacity }} className="absolute top-5 right-5 z-10 rotate-12 pointer-events-none text-mono font-bold border-2 rounded-[var(--radius-md)] px-2.5 py-1 border-[var(--agree)] text-[var(--agree)]">
            SAVE
          </motion.div>
          <motion.div style={{ opacity: glowLeftOpacity }} className="absolute top-5 left-5 z-10 -rotate-12 pointer-events-none text-mono font-bold border-2 rounded-[var(--radius-md)] px-2.5 py-1 border-[var(--dismiss)] text-[var(--dismiss)]">
            SKIP
          </motion.div>
        </>
      )}

      {/* Card content — fills the card; no competing height math */}
      <div className={cn("p-4 flex flex-col h-full", !isTop && "invisible")}>
        {/* Header: topic badge (+ tier badge) + agreement */}
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 flex-wrap min-w-0">
            <Badge variant="topic" size="md" color={topicColor}>
              {card.topic_name}
            </Badge>
            {/* #78: provenance badge — nothing for a news card. */}
            <SourceTierBadge
              sourceType={card.source_type}
              authorName={card.author_name}
              credibilityScore={card.credibility_score}
              isPreprint={card.is_preprint}
            />
          </span>
          <span className="text-mono inline-flex items-center gap-1.5" style={{ color: aColor }}>
            {pct}%
            <span className="inline-flex items-center gap-[2px]" aria-hidden="true">
              {Array.from({ length: 4 }, (_, i) => (
                <span
                  key={i}
                  className="inline-block w-1 h-1 rounded-full"
                  style={{ backgroundColor: i < filled ? aColor : "var(--text-ghost)", opacity: i < filled ? 1 : 0.4 }}
                />
              ))}
            </span>
          </span>
        </div>

        {/* Headline */}
        <h2 className="text-title text-[var(--text-primary)] mt-3 flex-shrink-0">
          {card.title}
        </h2>

        {/* Tension box — amber */}
        {card.tension_line && card.tension_line !== card.title && (
          <div className="mt-3 rounded-[var(--radius-md)] border border-[var(--accent-muted)] bg-[var(--accent-subtle)] px-3 py-2.5 flex items-start gap-2">
            <span className="text-[var(--accent)] shrink-0 mt-[2px]" aria-hidden="true">&#9888;</span>
            <p className="text-small text-emphasis text-[var(--accent)]">{card.tension_line}</p>
          </div>
        )}

        {/* Facts — top 3, clipped cleanly (never mid-line) */}
        <ul className="mt-4 space-y-2.5 flex-1 min-h-0 overflow-hidden">
          {card.facts.slice(0, 3).map((fact, i) => (
            <li key={i} className="text-small text-[var(--text-secondary)] flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-[7px]" style={{ backgroundColor: topicColor }} />
              <span className="line-clamp-2">{fact}</span>
            </li>
          ))}
        </ul>

        {/* Source chips — pinned to the card bottom */}
        <div className="flex items-center gap-1.5 flex-wrap mt-auto pt-3 border-t border-[var(--glass-border)]">
          {card.sources.slice(0, 3).map((s) => (
            <span key={s} className="text-mono text-[10px] px-2 py-0.5 rounded-full bg-[var(--surface-raised)] text-[var(--text-secondary)]">
              {s}
            </span>
          ))}
          {card.sources.length > 3 && (
            <span className="text-mono text-[10px] px-2 py-0.5 rounded-full bg-[var(--surface-raised)] text-[var(--text-muted)]">
              +{card.sources.length - 3}
            </span>
          )}
          {/* #83: opt-in "Follow source" for gated cards. stop pointer-capture so the tap never
              starts a drag/swipe. */}
          {card.is_gated && card.source_id != null && (
            <button
              type="button"
              onPointerDownCapture={(e) => e.stopPropagation()}
              onClick={followSource}
              aria-pressed={followed}
              className={cn(
                "ml-auto text-mono text-[10px] px-2.5 py-1 rounded-full border transition-colors",
                followed
                  ? "border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              )}
            >
              {followed ? "Following" : "Follow source"}
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
