"use client";

import { useEffect, useState } from "react";
import { getConsensus, type ConsensusResult } from "@/lib/api";

/** Consensus / divergence (Wave B3): "N of M align" + the named dissent. Accepts a pre-fetched
 *  `data` prop; otherwise self-fetches. Hidden when unavailable. */
export function ConsensusRow({
  clusterId,
  data: provided,
}: {
  clusterId: number;
  data?: ConsensusResult;
}) {
  const [data, setData] = useState<ConsensusResult | "loading">(provided ?? "loading");

  useEffect(() => {
    if (provided !== undefined) {
      setData(provided);
      return;
    }
    let alive = true;
    getConsensus(clusterId)
      .then((r) => alive && setData(r))
      .catch(() => alive && setData({ unavailable: true }));
    return () => {
      alive = false;
    };
  }, [clusterId, provided]);

  if (data === "loading") return <div className="skeleton h-10 rounded-[var(--radius-md)]" />;
  if (data.unavailable) return null;

  const agree = data.agree_count ?? 0;
  const total = data.total ?? 0;
  const dissent = data.dissent ?? [];

  return (
    <div>
      <p className="text-small text-[var(--text-secondary)]">
        {agree} of {total} align
      </p>
      {dissent.length > 0 && (
        <div className="mt-2 rounded-[var(--radius-md)] bg-[var(--accent-subtle)] border-l-2 border-[var(--accent)] p-3">
          <div className="text-mono text-[var(--accent)] mb-1">WHERE THEY DIVERGE</div>
          {dissent.map((d, i) => (
            <p key={i} className="text-small text-[var(--text-secondary)]">
              {d.outlet}: {d.point}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
