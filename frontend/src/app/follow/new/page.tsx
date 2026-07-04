"use client";

/**
 * WS-2 (#112): "Follow anything" — a full-screen create page (NOT a modal; the app keeps its
 * zero-overlay pattern, hardware-back just works, identical on web). Type any phrase → a saved_search
 * follow → land on /following with the new rail already there (immediate payoff, even if empty).
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Chip } from "@/components/ui/Chip";
import { addFollow, getTopics } from "@/lib/api";

export default function FollowNewPage() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  // Suggestion chips: trending topic names (a warm start; the user can still type anything).
  useEffect(() => {
    getTopics()
      .then((t) => {
        const names = [...(t.trending_topics ?? []), ...(t.explore_topics ?? [])]
          .map((x) => x.name)
          .slice(0, 8);
        setSuggestions(names);
      })
      .catch(() => setSuggestions([]));
  }, []);

  const submit = useCallback(
    async (raw: string) => {
      const phrase = raw.trim();
      if (!phrase || saving) return;
      setSaving(true);
      setError(null);
      try {
        await addFollow("saved_search", phrase);
        router.replace("/following"); // rail is visible there immediately (even if empty)
      } catch (err) {
        // Backend inline errors: cap reached (400), etc. Show under the input, not a toast.
        const msg = err instanceof Error ? err.message : "Couldn't save — try again";
        setError(
          msg.includes("400")
            ? "You follow the maximum number of topics — unfollow one first."
            : "Couldn't save — check your connection and try again."
        );
        setSaving(false);
      }
    },
    [saving, router]
  );

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)] pt-[var(--space-lg)]">
      <h1 className="text-display text-[var(--text-primary)] mb-1">Follow anything</h1>
      <p className="text-small text-[var(--text-muted)] mb-[var(--space-lg)]">
        A topic, a company, an event — we watch every source for it and gather the coverage.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(value);
        }}
      >
        <Input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="US–Iran war, AI chips, your city…"
          maxLength={255}
          aria-label="Topic to follow"
        />
        {error && (
          <p role="alert" className="text-mono text-[var(--dismiss)] mt-2">
            {error}
          </p>
        )}

        {suggestions.length > 0 && (
          <div className="mt-[var(--space-md)]">
            <p className="text-category text-[var(--text-muted)] mb-2">TRENDING</p>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <Chip key={s} onClick={() => void submit(s)}>
                  {s}
                </Chip>
              ))}
            </div>
          </div>
        )}

        <Button
          type="submit"
          variant="primary"
          disabled={!value.trim() || saving}
          loading={saving}
          className="mt-[var(--space-lg)] w-full"
        >
          Follow
        </Button>
      </form>
    </div>
  );
}
