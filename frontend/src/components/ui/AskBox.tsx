"use client";

import { useState } from "react";
import { askStory, isAskAnswer, type AskAnswer } from "@/lib/api";

type State = "idle" | "thinking" | "answered" | "error";

/** "Ask this story" — grounded, cited Q&A (Wave B1). POST /clusters/{id}/ask. */
export function AskBox({ clusterId }: { clusterId: number }) {
  const [q, setQ] = useState("");
  const [state, setState] = useState<State>("idle");
  const [result, setResult] = useState<AskAnswer | null>(null);

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const question = q.trim();
    if (!question) return;
    setState("thinking");
    setResult(null);
    try {
      const r = await askStory(clusterId, question);
      if (isAskAnswer(r)) {
        setResult(r);
        setState("answered");
      } else {
        setState("error");
      }
    } catch {
      setState("error");
    }
  }

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-md)]">
      <form onSubmit={submit} className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          maxLength={500}
          placeholder="Ask about this story — impact, sources, what changed…"
          aria-label="Ask about this story"
          className="flex-1 bg-[var(--surface-raised)] rounded-[var(--radius-md)] px-3 py-2 text-small text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:ring-2 focus:ring-[var(--accent)]"
        />
        <button
          type="submit"
          aria-label="Ask"
          disabled={state === "thinking"}
          className="rounded-[var(--radius-md)] bg-[var(--accent)] text-[var(--bg)] px-4 py-2 text-small font-medium disabled:opacity-60"
        >
          {state === "thinking" ? "…" : "Ask"}
        </button>
      </form>

      {state === "thinking" && (
        <div className="skeleton h-16 rounded-[var(--radius-md)] mt-3" aria-live="polite" />
      )}

      {state === "answered" && result && (
        <div className="mt-3" aria-live="polite">
          {result.refused || !result.answer.trim() ? (
            <p className="text-small text-[var(--text-muted)]">
              Not covered in these sources.
            </p>
          ) : (
            <>
              <p className="text-small text-[var(--text-primary)] leading-relaxed">
                {result.answer}
              </p>
              {result.citations.length > 0 && (
                <p className="text-mono text-[10px] text-[var(--text-ghost)] mt-2">
                  SOURCES · {result.citations.map((c) => c.source).join(" · ")}
                </p>
              )}
            </>
          )}
        </div>
      )}

      {state === "error" && (
        <p className="text-small text-[var(--text-muted)] mt-3" aria-live="polite">
          Couldn&apos;t answer right now — try again.
        </p>
      )}
    </div>
  );
}
