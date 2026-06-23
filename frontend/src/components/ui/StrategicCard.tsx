"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getClusterStrategic, type LensResult } from "@/lib/api";

interface Actor {
  name: string;
  incentive: string;
  likely_move: string;
}

/** E7 — game-theory / strategic lens on Deep Dive. Data: GET /clusters/{id}/strategic.
 *  Hides itself when unavailable (graceful). Drill (violet) accent. */
export function StrategicCard({ clusterId }: { clusterId: number }) {
  const [data, setData] = useState<LensResult | "loading">("loading");

  useEffect(() => {
    let alive = true;
    getClusterStrategic(clusterId)
      .then((r) => alive && setData(r))
      .catch(() => alive && setData({ unavailable: true }));
    return () => {
      alive = false;
    };
  }, [clusterId]);

  if (data === "loading") {
    return <div className="skeleton h-24 rounded-[var(--radius-lg)]" />;
  }
  if (data.unavailable) return null;

  const actors = Array.isArray(data.actors) ? (data.actors as Actor[]) : [];
  const gameType = typeof data.game_type === "string" ? data.game_type : null;
  const secondOrder = Array.isArray(data.second_order) ? (data.second_order as string[]) : [];
  const take = typeof data.non_obvious_take === "string" ? data.non_obvious_take : null;
  if (!actors.length && !take) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface)] p-[var(--space-md)]"
    >
      <div className="flex items-center justify-between mb-3 gap-2">
        <span className="text-mono" style={{ color: "var(--drill)" }}>
          THE STRATEGIC READ
        </span>
        {gameType && (
          <span
            className="text-mono text-[10px] px-2 py-0.5 rounded-full shrink-0"
            style={{ background: "var(--drill-muted)", color: "var(--drill)" }}
          >
            {gameType}
          </span>
        )}
      </div>

      {actors.length > 0 && (
        <div className="flex flex-col gap-2.5 mb-3">
          {actors.map((a, i) => (
            <div key={i} className="text-small">
              <span className="text-[var(--text-primary)] font-medium">{a.name}</span>
              {a.incentive && <span className="text-[var(--text-muted)]"> — {a.incentive}</span>}
              {a.likely_move && (
                <p className="text-[var(--text-secondary)] mt-0.5">&#8627; {a.likely_move}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {secondOrder.length > 0 && (
        <ul className="flex flex-col gap-1 mb-3">
          {secondOrder.map((s, i) => (
            <li key={i} className="text-small text-[var(--text-secondary)] flex gap-2">
              <span style={{ color: "var(--drill)" }} className="shrink-0">&bull;</span>
              <span>{s}</span>
            </li>
          ))}
        </ul>
      )}

      {take && (
        <p
          className="text-small text-emphasis text-[var(--text-primary)] border-l-2 pl-3"
          style={{ borderColor: "var(--drill)" }}
        >
          {take}
        </p>
      )}

      <p className="text-mono text-[10px] text-[var(--text-ghost)] mt-3">
        AI-generated &middot; a game-theory lens, not advice
      </p>
    </motion.div>
  );
}
