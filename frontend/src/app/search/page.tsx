"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Input } from "@/components/ui/Input";
import { Chip } from "@/components/ui/Chip";
import { FollowButton } from "@/components/ui/FollowButton";
import { search, type SearchResultItem } from "@/lib/api";
import { storyHref } from "@/lib/utils";

type FilterKey = "all" | "semantic" | "topic" | "recent";
const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "semantic", label: "Semantic" },
  { key: "topic", label: "Topic" },
  { key: "recent", label: "Recent" },
];

const SearchIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" />
    <path d="M21 21l-4.35-4.35" />
  </svg>
);

function matchedLabel(matchedOn: string): string {
  if (matchedOn.includes("topic") && matchedOn.includes("meaning")) return "matched: both";
  if (matchedOn.includes("topic")) return "matched: topic";
  return "matched: meaning";
}

const RECENT_KEY = "newslens-recent-searches";
const RECENT_MAX = 5;

function readRecent(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => {
    setRecent(readRecent());
  }, []);

  function rememberQuery(q: string) {
    setRecent((prev) => {
      const next = [q, ...prev.filter((x) => x.toLowerCase() !== q.toLowerCase())].slice(
        0,
        RECENT_MAX
      );
      if (typeof window !== "undefined") {
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      }
      return next;
    });
  }

  async function runSearch(q: string) {
    const trimmed = q.trim();
    if (!trimmed) return;
    setState("loading");
    setSubmitted(trimmed);
    setQuery(trimmed);
    rememberQuery(trimmed);
    try {
      const res = await search(trimmed);
      setResults(res.results);
      setState("done");
    } catch {
      setResults([]);
      setState("error");
    }
  }

  const filtered = results.filter((r) => {
    if (filter === "semantic") return r.matched_on.includes("meaning");
    if (filter === "topic") return r.matched_on.includes("topic");
    return true;
  });

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-lg)] py-[var(--space-lg)]">
      <h1 className="text-hero text-[var(--text-primary)] mb-[var(--space-md)]">Search</h1>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          runSearch(query);
        }}
      >
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the news"
          leftIcon={<SearchIcon />}
          aria-label="Search the news"
          autoFocus
        />
      </form>

      <div className="flex gap-2 mt-[var(--space-md)] overflow-x-auto no-scrollbar">
        {FILTERS.map((f) => (
          <Chip key={f.key} selected={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}
          </Chip>
        ))}
      </div>

      <div className="mt-[var(--space-lg)]">
        {state === "loading" && (
          <p className="text-mono text-[var(--text-muted)]">Searching…</p>
        )}
        {state === "error" && (
          <p className="text-small text-[var(--text-muted)]">
            Couldn&apos;t run that search. Try again.
          </p>
        )}
        {state === "idle" && (
          <div className="flex flex-col gap-[var(--space-lg)]">
            {recent.length > 0 && (
              <div>
                <p className="text-mono text-[var(--text-ghost)] mb-[var(--space-sm)]">
                  RECENT
                </p>
                <div className="flex flex-wrap gap-2">
                  {recent.map((q) => (
                    <Chip key={q} onClick={() => runSearch(q)}>
                      {q}
                    </Chip>
                  ))}
                </div>
              </div>
            )}
            <p className="text-small text-[var(--text-muted)]">
              Search across every source — by topic or by meaning.
            </p>
          </div>
        )}
        {state === "done" && (
          <>
            <div className="flex items-center justify-between gap-3 mb-[var(--space-md)]">
              <p className="text-mono text-[var(--text-muted)]">
                &ldquo;{submitted}&rdquo; &middot; {filtered.length}{" "}
                {filtered.length === 1 ? "result" : "results"}
              </p>
              {submitted && (
                <FollowButton
                  key={submitted}
                  kind="saved_search"
                  value={submitted}
                  label="Follow this search"
                />
              )}
            </div>
            {filtered.length === 0 ? (
              <p className="text-small text-[var(--text-muted)]">
                No stories match &mdash; try a broader query.
              </p>
            ) : (
              <div className="flex flex-col gap-[var(--space-md)]">
                <AnimatePresence initial={false}>
                  {filtered.map((r, i) => (
                    <motion.div
                      key={r.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2, delay: i * 0.03 }}
                    >
                      <Link
                        href={r.cluster_id ? storyHref(r.cluster_id) : r.url}
                        className="block rounded-[var(--radius-lg)] bg-[var(--surface)] border border-[var(--border-subtle)] p-[var(--space-md)] transition-colors hover:bg-[var(--surface-hover)]"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <h2 className="text-heading text-[var(--text-primary)]">
                            {r.title}
                          </h2>
                          <span className="shrink-0 text-mono text-[10px] px-2 py-0.5 rounded-full bg-[var(--accent-subtle)] text-[var(--accent)]">
                            {matchedLabel(r.matched_on)}
                          </span>
                        </div>
                        {r.snippet && (
                          <p className="text-small text-[var(--text-secondary)] line-clamp-2 mt-1.5">
                            {r.snippet}
                          </p>
                        )}
                        <p className="text-mono text-[var(--text-muted)] mt-2">
                          {r.source?.name}
                        </p>
                      </Link>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
