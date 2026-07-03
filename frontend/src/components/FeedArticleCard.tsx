"use client";

import Link from "next/link";
import { SourceTierBadge } from "@/components/ui/SourceTierBadge";
import { relativeTime, storyHref } from "@/lib/utils";
import type { Article } from "@/lib/api";

/** #93 — a feed row for an `Article` (distinct from the briefing's `BriefingStory`). Clustered
 *  articles open the deep dive; unclustered ones link out to the source. Research/expert rows are
 *  badged; plain news rows are unadorned. */
export function FeedArticleCard({ article }: { article: Article }) {
  const clustered = article.cluster_id != null;
  const body = (
    <>
      <h3 className="text-heading text-[var(--text-primary)] leading-snug">{article.title}</h3>
      {article.snippet && (
        <p className="text-small text-[var(--text-secondary)] mt-1 line-clamp-2">{article.snippet}</p>
      )}
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        <span className="text-mono text-[var(--text-muted)]">{article.source.name}</span>
        {article.published_at && (
          <span className="text-mono text-[var(--text-ghost)]">{relativeTime(article.published_at)}</span>
        )}
        <SourceTierBadge
          sourceType={article.source.source_type}
          authorName={article.source.author_name}
          credibilityScore={article.source.credibility_score}
          isPreprint={article.source.is_preprint}
        />
      </div>
    </>
  );

  const cls =
    "block py-4 border-b border-[var(--border-subtle)] -mx-4 px-4 rounded-[var(--radius-md)] transition-colors hover:bg-[var(--accent-subtle)]";

  return clustered ? (
    <Link href={storyHref(article.cluster_id as number)} className={cls}>
      {body}
    </Link>
  ) : (
    <a href={article.url} target="_blank" rel="noopener noreferrer" className={cls}>
      {body}
    </a>
  );
}
