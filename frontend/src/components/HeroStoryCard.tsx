"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { articleHref, relativeTime, storyHref } from "@/lib/utils";
import type { BriefingStory } from "@/lib/api";

interface HeroStoryCardProps {
  story: BriefingStory;
}

export function HeroStoryCard({ story }: HeroStoryCardProps) {
  // Clustered → deep dive; unclustered fallback → single-article view; neither → inert.
  const href =
    story.cluster_id != null
      ? storyHref(story.cluster_id)
      : story.article_id != null
        ? articleHref(story.article_id)
        : null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -3 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <Link
        href={href ?? "#"}
        aria-disabled={href === null}
        style={href === null ? { pointerEvents: "none" } : undefined}
        className="block gradient-border rounded-[var(--radius-lg)] p-4 transition-all duration-[var(--duration-short)] hover:shadow-[var(--shadow-md)]"
      >
        <div className="flex items-center gap-2 mb-3">
          <Badge variant="accent" size="md">
            {story.category || "Top Story"}
          </Badge>
          {!story.is_read && <Badge variant="dot" />}
        </div>

        <h2 className="text-hero text-[var(--text-primary)] mb-2">
          {story.title}
        </h2>

        <p className="text-body text-[var(--text-secondary)] line-clamp-2 mb-3">
          {story.summary}
        </p>

        {/* "Why you're seeing this" — WIIFM one-liner, when cached (Wave Q1) */}
        {story.impact_headline && (
          <p className="text-mono text-[var(--accent)] line-clamp-1 mb-3">
            {story.impact_headline}
          </p>
        )}

        <div className="flex items-center gap-3">
          <ConfidenceScore
            sourceCount={story.source_count}
            coherence={story.coherence}
          />
          <span className="text-mono text-[var(--text-ghost)]">
            {relativeTime(new Date().toISOString())}
          </span>
        </div>
      </Link>
    </motion.div>
  );
}
