"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/Button";
import {
  getFollows,
  removeFollow,
  type FollowItem,
  type FollowKind,
} from "@/lib/api";

type PageState = "loading" | "success" | "empty" | "error";

// Friendly labels — never surface the raw `kind` enum to the reader.
const KIND_LABEL: Record<FollowKind, string> = {
  topic: "Topic",
  entity: "Entity",
  saved_search: "Search",
};

export default function FollowingPage() {
  const [state, setState] = useState<PageState>("loading");
  const [follows, setFollows] = useState<FollowItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchFollows = useCallback(async () => {
    try {
      setState("loading");
      setError(null);
      const data = await getFollows();
      if (!data || data.length === 0) {
        setFollows([]);
        setState("empty");
        return;
      }
      setFollows(data);
      setState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load your follows");
      setState("error");
    }
  }, []);

  useEffect(() => {
    fetchFollows();
  }, [fetchFollows]);

  const handleUnfollow = async (id: number) => {
    const prev = follows;
    const next = follows.filter((f) => f.id !== id);
    setFollows(next); // optimistic
    if (next.length === 0) setState("empty");
    try {
      await removeFollow(id);
    } catch {
      setFollows(prev); // rollback
      setState("success");
    }
  };

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)]">
      {/* Loading */}
      {state === "loading" && (
        <div className="pt-4 space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-16 w-full rounded-[var(--radius-md)]" />
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
          <p className="text-heading text-[var(--text-primary)]">Unable to load your follows</p>
          {error && <p className="text-mono text-[var(--dismiss)] mt-1">{error}</p>}
          <Button variant="secondary" onClick={fetchFollows} className="mt-3">
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
              <path d="M12 5v14M5 12h14" />
            </svg>
          </motion.div>
          <p className="text-heading text-[var(--text-primary)]">Not following anything yet</p>
          <p className="text-small text-[var(--text-muted)] mt-1.5 max-w-[280px]">
            Follow a topic from your briefing, or save a search to keep tracking it here.
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

      {/* List */}
      {state === "success" && (
        <div className="pt-3">
          <div className="flex items-baseline justify-between mb-3">
            <h1 className="text-hero text-[var(--text-primary)]">Following</h1>
            <span className="text-mono text-[var(--text-ghost)]">
              {follows.length} {follows.length === 1 ? "follow" : "follows"}
            </span>
          </div>

          <AnimatePresence>
            {follows.map((f) => (
              <motion.div
                key={f.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -100 }}
                transition={{ duration: 0.2 }}
              >
                <div className="py-3 border-b border-[var(--border-subtle)]">
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-mono text-[var(--text-ghost)] uppercase mb-0.5">
                        {KIND_LABEL[f.kind]}
                      </p>
                      <p className="text-title text-[var(--text-primary)] truncate">
                        {f.value}
                      </p>
                    </div>

                    {/* One-tap unfollow — amber "Following" chip; tapping removes it */}
                    <button
                      onClick={() => handleUnfollow(f.id)}
                      aria-label={`Unfollow ${f.value}`}
                      className="shrink-0 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-mono whitespace-nowrap border border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)] hover:brightness-110 transition-[filter,colors] duration-[var(--duration-short)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      <span>Following</span>
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
