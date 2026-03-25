"use client";

import Link from "next/link";
import { ConfidenceScore } from "@/components/ui/ConfidenceScore";
import { relativeTime } from "@/lib/utils";
import type { BriefingStory } from "@/lib/api";

interface StoryCardProps {
  story: BriefingStory;
}

export function StoryCard({ story }: StoryCardProps) {
  return (
    <Link
      href={`/story/${story.cluster_id}`}
      className="block py-[var(--space-xl)] border-b border-[var(--story-separator)] transition-colors hover:bg-[var(--accent-subtle)]"
    >
      <div className="flex items-start gap-2">
        {/* Unread dot */}
        {!story.is_read && (
          <span
            className="mt-[7px] w-[6px] h-[6px] rounded-full bg-[var(--story-unread-color)] shrink-0"
            aria-label="Unread"
          />
        )}

        <div className="flex-1 min-w-0">
          {/* Title */}
          <h3 className="text-heading text-[var(--story-title-color)]">
            {story.title}
          </h3>

          {/* Summary */}
          <p className="text-small text-[var(--story-summary-color)] mt-1 line-clamp-2">
            {story.summary}
          </p>

          {/* Metadata row */}
          <div className="flex items-center gap-3 mt-2">
            <ConfidenceScore
              sourceCount={story.source_count}
              coherence={story.coherence}
            />
          </div>
        </div>
      </div>
    </Link>
  );
}
