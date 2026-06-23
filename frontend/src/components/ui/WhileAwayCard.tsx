"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getDigest, type Digest } from "@/lib/api";
import { storyHref } from "@/lib/utils";

/** "While you were away" (Wave C): the in-app return trigger. Shows clusters formed since the
 *  last visit with their cached WIIFM headline. Hidden when caught up. */
export function WhileAwayCard() {
  const [digest, setDigest] = useState<Digest | null>(null);

  useEffect(() => {
    let alive = true;
    getDigest()
      .then((d) => alive && setDigest(d))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  if (!digest || digest.count === 0) return null;

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--accent-muted)] bg-[var(--accent-subtle)] p-[var(--space-md)] mb-6">
      <div className="text-mono text-[var(--accent)] mb-2">WHILE YOU WERE AWAY</div>
      <div className="flex flex-col gap-2.5">
        {digest.items.map((i) => (
          <Link key={i.cluster_id} href={storyHref(i.cluster_id)} className="block">
            <p className="text-small text-[var(--text-primary)] leading-snug">{i.title}</p>
            {i.headline && (
              <p className="text-mono text-[10px] text-[var(--accent)] mt-0.5">{i.headline}</p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
