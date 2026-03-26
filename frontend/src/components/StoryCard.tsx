"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/Badge";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { relativeTime } from "@/lib/utils";
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <Link
        href={`/story/${story.cluster_id}`}
        className="flex gap-3 py-4 border-b border-[var(--border-subtle)] transition-colors hover:bg-[var(--accent-subtle)] -mx-4 px-4 rounded-[var(--radius-md)]"
      >
        {/* Category color indicator */}
        <div
          className="w-[3px] rounded-full shrink-0 mt-1"
          style={{ backgroundColor: topicColor, height: "calc(100% - 8px)" }}
        />

        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-start gap-2">
            {!story.is_read && (
              <span className="mt-2 shrink-0">
                <Badge variant="dot" />
              </span>
            )}
            <h3 className="text-heading text-[var(--text-primary)] flex-1">
              {story.title}
            </h3>
          </div>

          {/* Summary */}
          <p className="text-small text-[var(--text-secondary)] mt-1 line-clamp-2">
            {story.summary}
          </p>

          {/* Meta row */}
          <div className="flex items-center gap-3 mt-2">
            <ConfidenceScore
              sourceCount={story.source_count}
              coherence={story.coherence}
            />
            <span className="text-mono text-[var(--text-ghost)]">
              {story.category}
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}
