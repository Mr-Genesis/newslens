"use client";

import { useEffect, useState } from "react";
import { getFrameworks, type FrameworksResult } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Show-the-working framework chips (Wave B2). Tap a chip for its ≤20-word line.
 *  Accepts a pre-fetched `data` prop; otherwise self-fetches. Hidden when none fire. */
export function FrameworksCard({
  clusterId,
  data: provided,
}: {
  clusterId: number;
  data?: FrameworksResult;
}) {
  const [data, setData] = useState<FrameworksResult | "loading">(provided ?? "loading");
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    if (provided !== undefined) {
      setData(provided);
      return;
    }
    let alive = true;
    getFrameworks(clusterId)
      .then((r) => alive && setData(r))
      .catch(() => alive && setData({ unavailable: true }));
    return () => {
      alive = false;
    };
  }, [clusterId, provided]);

  if (data === "loading") return <div className="skeleton h-10 rounded-[var(--radius-md)]" />;
  if (data.unavailable || !data.frameworks || data.frameworks.length === 0) return null;

  const open = data.frameworks.find((f) => f.id === openId);

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {data.frameworks.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setOpenId(openId === f.id ? null : f.id)}
            className={cn(
              "text-mono px-3 py-1.5 rounded-full border transition-colors",
              openId === f.id
                ? "border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                : "border-[var(--border)] text-[var(--text-secondary)]"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>
      {open && (
        <p className="text-small text-[var(--text-primary)] leading-relaxed mt-3 pl-3 border-l-2 border-[var(--accent)]">
          {open.one_liner}
        </p>
      )}
    </div>
  );
}
