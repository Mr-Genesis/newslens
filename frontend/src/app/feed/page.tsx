"use client";

import { useCallback, useEffect, useState } from "react";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { FeedArticleCard } from "@/components/FeedArticleCard";
import { getFeed, type Article } from "@/lib/api";

type SourceType = "all" | "news" | "research" | "expert";
const CHIPS: { label: string; value: SourceType }[] = [
  { label: "All", value: "all" },
  { label: "News", value: "news" },
  { label: "Research", value: "research" },
  { label: "Experts", value: "expert" },
];
type State = "loading" | "success" | "empty" | "error";

/** #82 — the source-type-filtered feed screen. The backend GET /feed?source_type= + getFeed(sourceType)
 *  already exist; this is the surface that renders them. */
export default function FeedPage() {
  const [active, setActive] = useState<SourceType>("all");
  const [articles, setArticles] = useState<Article[]>([]);
  const [state, setState] = useState<State>("loading");

  const load = useCallback(async (type: SourceType) => {
    setState("loading");
    try {
      const res = await getFeed(1, 20, undefined, type === "all" ? undefined : type);
      setArticles(res.articles);
      setState(res.articles.length ? "success" : "empty");
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    void load(active);
  }, [active, load]);

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)] pt-2">
      <h1 className="text-hero text-[var(--text-primary)] mb-3">Feed</h1>
      <div className="flex gap-2 overflow-x-auto pb-3 -mx-4 px-4" role="group" aria-label="Filter by source type">
        {CHIPS.map((c) => (
          <Chip key={c.value} selected={active === c.value} onClick={() => setActive(c.value)}>
            {c.label}
          </Chip>
        ))}
      </div>

      {state === "loading" && <p className="text-small text-[var(--text-muted)] pt-6">Loading…</p>}

      {state === "error" && (
        <div className="pt-6">
          <p className="text-small text-[var(--dismiss)]">Couldn&apos;t load the feed.</p>
          <Button variant="secondary" onClick={() => load(active)} className="mt-3">
            Try again
          </Button>
        </div>
      )}

      {state === "empty" && (
        <p className="text-small text-[var(--text-muted)] pt-6">Nothing here yet — check back soon.</p>
      )}

      {state === "success" && (
        <div className="flex flex-col" key={active}>
          {articles.map((a) => (
            <FeedArticleCard key={a.id} article={a} />
          ))}
        </div>
      )}
    </div>
  );
}
