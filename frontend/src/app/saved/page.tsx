"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  getSavedArticles,
  unsaveArticle,
  type SavedArticle,
} from "@/lib/api";
import { relativeTime } from "@/lib/utils";

type PageState = "loading" | "success" | "empty" | "error";

export default function SavedPage() {
  const [state, setState] = useState<PageState>("loading");
  const [articles, setArticles] = useState<SavedArticle[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchSaved = useCallback(async () => {
    try {
      setState("loading");
      setError(null);
      const data = await getSavedArticles();
      if (!data.articles || data.articles.length === 0) {
        setState("empty");
        return;
      }
      setArticles(data.articles);
      setState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load saved stories");
      setState("error");
    }
  }, []);

  useEffect(() => {
    fetchSaved();
  }, [fetchSaved]);

  const handleUnsave = async (articleId: number) => {
    try {
      await unsaveArticle(articleId);
      setArticles((prev) => prev.filter((a) => a.article_id !== articleId));
      if (articles.length <= 1) {
        setState("empty");
      }
    } catch {
      // Silent failure
    }
  };

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)]">
      {/* Loading */}
      {state === "loading" && (
        <div className="pt-4 space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-20 w-full rounded-[var(--radius-md)]" />
          ))}
        </div>
      )}

      {/* Error */}
      {state === "error" && (
        <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
          <div className="w-12 h-12 rounded-full bg-[var(--dismiss-muted)] flex items-center justify-center mb-3">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--dismiss)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <p className="text-heading text-[var(--text-primary)]">Unable to load saved stories</p>
          {error && <p className="text-mono text-[var(--dismiss)] mt-1">{error}</p>}
          <Button variant="secondary" onClick={fetchSaved} className="mt-3">
            Try again
          </Button>
        </div>
      )}

      {/* Empty */}
      {state === "empty" && (
        <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3 }}
            className="w-12 h-12 rounded-full bg-[var(--accent-subtle)] flex items-center justify-center mb-3"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
          </motion.div>
          <p className="text-heading text-[var(--text-primary)]">No saved stories yet</p>
          <p className="text-small text-[var(--text-muted)] mt-1.5 max-w-[260px]">
            Tap the bookmark icon on any story to save it here
          </p>
          <Button
            variant="secondary"
            onClick={() => (window.location.href = "/")}
            className="mt-4"
          >
            Browse stories
          </Button>
        </div>
      )}

      {/* Saved articles list */}
      {state === "success" && (
        <div className="pt-3">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-heading text-[var(--text-primary)]">
              Saved Stories
            </h1>
            <span className="text-mono text-[var(--text-ghost)]">
              {articles.length} saved
            </span>
          </div>

          <AnimatePresence>
            {articles.map((article) => (
              <motion.div
                key={article.article_id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -100 }}
                transition={{ duration: 0.2 }}
              >
                <div className="py-3 border-b border-[var(--border-subtle)]">
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      {article.cluster_id ? (
                        <Link
                          href={`/story/${article.cluster_id}`}
                          className="text-heading text-[var(--text-primary)] line-clamp-2 hover:text-[var(--accent)] transition-colors"
                        >
                          {article.title}
                        </Link>
                      ) : (
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-heading text-[var(--text-primary)] line-clamp-2 hover:text-[var(--accent)] transition-colors"
                        >
                          {article.title}
                        </a>
                      )}
                      {article.snippet && (
                        <p className="text-small text-[var(--text-secondary)] mt-1 line-clamp-1">
                          {article.snippet}
                        </p>
                      )}
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className="text-mono text-[var(--text-ghost)]">
                          {article.source_name}
                        </span>
                        <span className="text-mono text-[var(--text-ghost)]">&middot;</span>
                        <span className="text-mono text-[var(--text-ghost)]">
                          {relativeTime(article.saved_at)}
                        </span>
                      </div>
                    </div>

                    {/* Unsave button */}
                    <button
                      onClick={() => handleUnsave(article.article_id)}
                      className="shrink-0 w-9 h-9 flex items-center justify-center rounded-full hover:bg-[var(--surface-raised)] transition-colors"
                      aria-label="Remove from saved"
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="var(--accent)" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                      </svg>
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
