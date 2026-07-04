"use client";

/**
 * WS-8 (#118): the Settings "System" card — a read-only window on GET /pipeline. Shows article counts
 * by embedding status, clusters, and last fetch in mono. Cold start reads "waking the pipeline…"; a
 * stale last-fetch row is tinted; an unreachable pipeline shows the dimmed last-known (or a plain
 * "unreachable" on a cold failure).
 */
import { useEffect, useRef, useState } from "react";

import { Card } from "@/components/ui/Card";
import { getPipeline, type PipelineStatus } from "@/lib/api";
import { relativeTime, cn } from "@/lib/utils";

const STALE_MINUTES = 45;

function isStale(iso: string | null): boolean {
  if (!iso) return true;
  return (Date.now() - new Date(iso).getTime()) / 60000 > STALE_MINUTES;
}

function Row({ label, value, tinted }: { label: string; value: string | number; tinted?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-mono text-[var(--text-muted)]">{label}</span>
      <span className={cn("text-mono", tinted ? "text-[var(--accent)]" : "text-[var(--text-secondary)]")}>
        {value}
      </span>
    </div>
  );
}

export function SystemCard() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const lastGood = useRef<PipelineStatus | null>(null);

  useEffect(() => {
    getPipeline()
      .then((s) => {
        lastGood.current = s;
        setStatus(s);
        setState("ok");
      })
      .catch(() => setState("error"));
  }, []);

  const shell = (children: React.ReactNode, dim = false) => (
    <Card variant="raised">
      <div className={cn("p-3.5", dim && "opacity-60")}>
        <h2 className="text-category text-[var(--text-muted)] mb-2">SYSTEM</h2>
        {children}
      </div>
    </Card>
  );

  if (state === "loading") {
    return shell(<p className="text-mono text-[var(--text-ghost)]">Waking the pipeline…</p>);
  }

  // Unreachable: dim the last-known snapshot if we have one, else say so plainly.
  const s = status ?? lastGood.current;
  if (state === "error" && !s) {
    return shell(<p className="text-mono text-[var(--text-ghost)]">Pipeline unreachable</p>);
  }
  if (!s) return shell(<p className="text-mono text-[var(--text-ghost)]">No data</p>);

  const stale = isStale(s.freshness.latest_article_fetched_at);
  const by = s.articles.by_embedding_status;
  return shell(
    <>
      <div className="space-y-1">
        <Row label="Articles" value={s.articles.total} />
        <Row label="Embedded" value={by.complete ?? 0} />
        <Row label="Pending" value={by.pending ?? 0} />
        <Row label="Failed" value={by.failed ?? 0} tinted={(by.failed ?? 0) > 0} />
        <Row label="Clusters" value={s.clusters.total} />
        <Row
          label="Last fetch"
          value={s.freshness.latest_article_fetched_at ? relativeTime(s.freshness.latest_article_fetched_at) : "—"}
          tinted={stale}
        />
      </div>
      {s.last_embedding_error && (
        <p className="text-mono text-[var(--dismiss)] mt-2">error: {s.last_embedding_error}</p>
      )}
    </>,
    state === "error", // if a refresh failed but we have last-known, dim it
  );
}
