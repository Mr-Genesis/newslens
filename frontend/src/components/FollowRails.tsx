"use client";

/**
 * WS-2 (#112): the "News You Follow" home section — a horizontal PAGER of topic panels (Design Spec).
 * One panel per follow (~85% viewport, scroll-snap-x; a 3-up grid at ≥768px = the wire diagram).
 * Each panel: mono header + amber "N new" pill, ≤3 headline rows, "see all". Tapping a story or
 * "see all" clears that rail's badge (POST /seen) — scrolling past does NOT. Section hidden when the
 * user follows nothing (the "+" to start lives on /following and here in the header).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { getFollowRails, markFollowSeen, type FollowRail } from "@/lib/api";

function NewPill({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span
      aria-label={`${count} new stories`}
      className="text-mono text-[11px] tracking-wide px-2 py-0.5 rounded-full"
      style={{ background: "color-mix(in srgb, var(--accent) 12%, transparent)", color: "var(--accent)" }}
    >
      {count > 9 ? "9+" : count} NEW
    </span>
  );
}

function RailPanel({ rail, onOpen }: { rail: FollowRail; onOpen: (r: FollowRail, clusterId?: number) => void }) {
  return (
    <section
      className="snap-start shrink-0 w-[85%] md:w-auto rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--surface-1)] p-[var(--space-md)]"
      aria-label={`Rail: ${rail.value}`}
    >
      <header className="flex items-center justify-between mb-2 gap-2">
        <h3 className="text-category text-[var(--text-primary)] truncate">{rail.value}</h3>
        <NewPill count={rail.new_count} />
      </header>

      {rail.stories.length === 0 ? (
        <p className="text-small text-[var(--text-muted)] italic py-2">
          Nothing new — we&apos;re watching.
        </p>
      ) : (
        <ul className="space-y-2">
          {rail.stories.map((s) => (
            <li key={s.cluster_id}>
              <button
                onClick={() => onOpen(rail, s.cluster_id)}
                className="text-left w-full text-body text-[var(--text-primary)] line-clamp-2 hover:text-[var(--accent)] transition-colors"
              >
                {s.title}
              </button>
            </li>
          ))}
        </ul>
      )}

      {rail.total > rail.stories.length && (
        <button
          onClick={() => onOpen(rail)}
          className="text-mono text-[var(--text-muted)] hover:text-[var(--accent)] mt-2"
        >
          see all →
        </button>
      )}
    </section>
  );
}

export function FollowRails({
  onClusterIdsRendered,
  refreshSignal = 0,
}: {
  /** WS-3 (#113): report the cluster ids these rails render so the home feed can dedupe them out
   *  (cross-section precedence hero > rails > categories > feed). */
  onClusterIdsRendered?: (ids: number[]) => void;
  /** Unify A: bump to force a re-fetch (pull-to-refresh from the home page). */
  refreshSignal?: number;
} = {}) {
  const router = useRouter();
  const [rails, setRails] = useState<FollowRail[] | null>(null);
  // Ref so the fetch effect always calls the latest callback without re-fetching on every render.
  const onIdsRef = useRef(onClusterIdsRendered);
  onIdsRef.current = onClusterIdsRendered;

  const load = useCallback(() => {
    getFollowRails()
      .then((rs) => {
        setRails(rs);
        onIdsRef.current?.(rs.flatMap((r) => r.stories.map((s) => s.cluster_id)));
      })
      .catch(() => setRails([])); // a failed rails fetch must never break the briefing
  }, []);

  // Fetch on mount AND whenever pull-to-refresh bumps refreshSignal — so a follow/unfollow or new
  // stories show without an app relaunch.
  useEffect(() => {
    load();
  }, [load, refreshSignal]);

  // Revalidate on foreground (WebView/tab resume) — the classic SWR refresh moment. Re-fetching
  // replaces the whole rails payload, so an optimistically-cleared badge resolves to server truth.
  useEffect(() => {
    if (typeof document === "undefined") return;
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [load]);

  const onOpen = useCallback(
    (rail: FollowRail, clusterId?: number) => {
      // Clear the badge for THIS rail only, optimistically.
      if (rail.new_count > 0) {
        setRails((prev) =>
          prev ? prev.map((r) => (r.follow_id === rail.follow_id ? { ...r, new_count: 0 } : r)) : prev
        );
        void markFollowSeen(rail.follow_id).catch(() => {}); // fire-and-forget; server is source of truth
      }
      if (clusterId != null) {
        if (typeof sessionStorage !== "undefined") sessionStorage.setItem("nl_surface", "rail");
        router.push(`/story/${clusterId}`);
      } else {
        router.push("/following"); // "see all"
      }
    },
    [router]
  );

  // Loading (null) and no-follows (empty) both render nothing — the section only appears once the
  // user has rails. The "+" entry point lives on /following and in the section header below.
  if (!rails || rails.length === 0) return null;

  return (
    <section className="mb-5" aria-label="News you follow">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-category text-[var(--text-muted)]">NEWS YOU FOLLOW</h2>
        <button
          onClick={() => router.push("/follow/new")}
          aria-label="Follow a new topic"
          className="text-[var(--accent)] hover:opacity-80 text-lg leading-none px-1"
        >
          +
        </button>
      </div>
      <div className="flex md:grid md:grid-cols-3 gap-3 overflow-x-auto snap-x snap-mandatory -mx-[var(--space-md)] px-[var(--space-md)] pb-1 no-scrollbar">
        {rails.map((r) => (
          <RailPanel key={r.follow_id} rail={r} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}
