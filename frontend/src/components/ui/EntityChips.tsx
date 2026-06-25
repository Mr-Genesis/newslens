"use client";

import { useEffect, useState } from "react";
import {
  getClusterEntities,
  getEntityClusters,
  type ClusterEntity,
  type EntityCluster,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** G1 cast strip: who/what is in this story (salient entities, highest-salience first). Tap a chip
 *  to see other recent stories touching the same entity ("appears in"). Self-fetches; hidden when
 *  no entities (e.g. extraction off or not yet run). */
export function EntityChips({
  clusterId,
  data: provided,
}: {
  clusterId: number;
  data?: ClusterEntity[];
}) {
  const [data, setData] = useState<ClusterEntity[] | "loading">(provided ?? "loading");
  const [openId, setOpenId] = useState<number | null>(null);
  const [appearsIn, setAppearsIn] = useState<EntityCluster[] | "loading">("loading");

  useEffect(() => {
    if (provided !== undefined) {
      setData(provided);
      return;
    }
    let alive = true;
    getClusterEntities(clusterId)
      .then((r) => alive && setData(Array.isArray(r) ? r : []))
      .catch(() => alive && setData([]));
    return () => {
      alive = false;
    };
  }, [clusterId, provided]);

  if (data === "loading") return <div className="skeleton h-10 rounded-[var(--radius-md)]" />;
  if (data.length === 0) return null;

  function toggle(id: number) {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    setOpenId(id);
    setAppearsIn("loading");
    getEntityClusters(id)
      .then((r) => setAppearsIn(Array.isArray(r) ? r : []))
      .catch(() => setAppearsIn([]));
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {data.map((e) => (
          <button
            key={e.id}
            type="button"
            onClick={() => toggle(e.id)}
            className={cn(
              "text-mono px-3 py-1.5 rounded-full border transition-colors",
              openId === e.id
                ? "border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                : "border-[var(--border)] text-[var(--text-secondary)]"
            )}
          >
            {e.canonical_name}
          </button>
        ))}
      </div>
      {openId !== null && (
        <div className="text-small mt-3 pl-3 border-l-2 border-[var(--accent)]">
          {appearsIn === "loading" ? (
            <span className="text-[var(--text-tertiary)]">Loading…</span>
          ) : appearsIn.length === 0 ? (
            <span className="text-[var(--text-tertiary)]">No other recent stories yet.</span>
          ) : (
            <>
              <p className="text-[var(--text-tertiary)] mb-1">Also appears in</p>
              <ul className="space-y-1">
                {appearsIn.map((c) => (
                  <li key={c.cluster_id} className="text-[var(--text-primary)]">
                    {c.title}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
