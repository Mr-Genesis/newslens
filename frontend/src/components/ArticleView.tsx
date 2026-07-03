"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import DeepDiveView from "@/components/DeepDiveView";
import { Badge } from "@/components/ui/Badge";
import { getArticle, type ArticleDetail } from "@/lib/api";
import { relativeTime } from "@/lib/utils";

/**
 * Single-article detail for briefing-fallback stories (article not clustered yet).
 * If the server resolves a cluster for the article, upgrade straight to the deep dive.
 */
export function ArticleView({ articleId }: { articleId: number }) {
  const router = useRouter();
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    getArticle(articleId)
      .then((a) => {
        setArticle(a);
        setState("ready");
      })
      .catch(() => setState("error"));
  }, [articleId]);

  if (state === "loading") {
    return (
      <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)] py-6 space-y-4">
        <div className="skeleton h-8 w-3/4" />
        <div className="skeleton h-24 w-full" />
      </div>
    );
  }

  if (state === "error" || !article) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-body text-[var(--text-muted)]">Story unavailable — try again shortly.</p>
      </div>
    );
  }

  // The article got clustered since the briefing was built — show the real deep dive.
  if (article.cluster_id != null) {
    return <DeepDiveView clusterIdOverride={article.cluster_id} />;
  }

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)] py-6">
      <button
        onClick={() => router.back()}
        className="min-h-12 flex items-center gap-1 text-mono uppercase text-[var(--text-secondary)] active:opacity-60 transition-opacity"
      >
        ← Back
      </button>

      <div className="flex items-center gap-2 mb-3 mt-2">
        <Badge variant="accent" size="md">
          {article.source_name}
        </Badge>
        {article.is_paywalled && (
          <Badge variant="paywall" size="md">
            Paywalled
          </Badge>
        )}
        {article.published_at && (
          <span className="text-mono text-[var(--text-ghost)]">
            {relativeTime(article.published_at)}
          </span>
        )}
      </div>

      <h1 className="text-h1 text-[var(--text-primary)] font-[family-name:var(--font-fraunces)] mb-4">
        {article.title}
      </h1>

      {article.snippet && (
        <p className="text-body text-[var(--text-secondary)] mb-6">{article.snippet}</p>
      )}

      <p className="text-mono text-[var(--text-ghost)] mb-4">
        This story is still being processed — the multi-source deep dive appears once related
        coverage is clustered.
      </p>

      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--accent)] px-5 py-3 text-small font-medium text-[#0C0C0E] transition-opacity hover:opacity-90"
      >
        Read the original →
      </a>
    </div>
  );
}
