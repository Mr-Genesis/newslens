"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { SourceTierBadge } from "@/components/ui/SourceTierBadge";
import { articleHref, cn, relativeTime, storyHref } from "@/lib/utils";
import type { BriefingStory } from "@/lib/api";

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

function getTopicColor(category: string): string {
  const lower = category.toLowerCase();
  return topicColorMap[lower] || "var(--topic-default)";
}

interface StoryCardProps {
  story: BriefingStory;
}

export function StoryCard({ story }: StoryCardProps) {
  const topicColor = getTopicColor(story.category || "");
  // Clustered → deep dive. Unclustered fallback → single-article view (/story?aid=N).
  // Only a story with NEITHER id renders inert.
  const href =
    story.cluster_id != null
      ? storyHref(story.cluster_id)
      : story.article_id != null
        ? articleHref(story.article_id)
        : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <Link
        href={href ?? "#"}
        aria-disabled={href === null}
        className={cn(
          "flex gap-3 py-4 border-b border-[var(--border-subtle)] transition-colors hover:bg-[var(--accent-subtle)] -mx-4 px-4 rounded-[var(--radius-md)]",
          !story.is_read && "bg-[var(--accent-subtle)]", // unread = subtle row tint (no layout shift)
          href === null && "pointer-events-none"
        )}
      >
        {/* Category color indicator */}
        <div
          className="w-[3px] rounded-full shrink-0 mt-1"
          style={{ backgroundColor: topicColor, height: "calc(100% - 8px)" }}
        />

        <div className="flex-1 min-w-0">
          {/* Title — flush-left always. Unread is signalled by the row tint + semibold title +
              the dot in the meta row, NOT a leading dot that indents the headline (device-QA #3). */}
          <h3
            className={cn(
              "text-heading text-[var(--text-primary)]",
              !story.is_read && "font-semibold"
            )}
          >
            {story.title}
          </h3>

          {/* Summary */}
          <p className="text-small text-[var(--text-secondary)] mt-1 line-clamp-2">
            {story.summary}
          </p>

          {/* "Why you're seeing this" — WIIFM one-liner, when cached (Wave Q1) */}
          {story.impact_headline && (
            <p className="text-mono text-[var(--accent)] mt-1.5 line-clamp-1">
              {story.impact_headline}
            </p>
          )}

          {/* Meta row — unread dot lives here (never beside the headline) */}
          <div className="flex items-center justify-between gap-3 mt-2">
            <span className="flex items-center gap-1.5">
              {!story.is_read && <Badge variant="dot" />}
              <ConfidenceScore
                sourceCount={story.source_count}
                coherence={story.coherence}
              />
            </span>
            <span className="flex items-center gap-1.5">
              {/* #78: "for your field" cue — RESEARCH/EXPERT badge on gated-tier stories. */}
              <SourceTierBadge sourceType={story.tier} />
              {story.region && story.region !== story.category && (
                <Badge variant="outline" size="sm">
                  {story.region.toUpperCase()}
                </Badge>
              )}
              {story.category && (
                <Badge variant="topic" size="sm" color={topicColor}>
                  {story.category.toUpperCase()}
                </Badge>
              )}
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}
