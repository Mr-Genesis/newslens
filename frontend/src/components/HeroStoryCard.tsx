"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { relativeTime, storyHref } from "@/lib/utils";
import type { BriefingStory } from "@/lib/api";

interface HeroStoryCardProps {
  story: BriefingStory;
}

export function HeroStoryCard({ story }: HeroStoryCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <Link
        href={storyHref(story.cluster_id)}
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
