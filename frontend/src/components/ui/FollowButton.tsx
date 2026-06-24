"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  addFollow,
  getFollows,
  removeFollow,
  type FollowItem,
  type FollowKind,
} from "@/lib/api";

interface FollowButtonProps {
  kind: FollowKind;
  value: string;
  /** Text for the unfollowed state. Defaults to "Follow". The followed state
   *  always reads "Following". */
  label?: string;
  className?: string;
  /** Fired after a successful toggle, with the new state. */
  onToggle?: (following: boolean) => void;
}

const norm = (s: string) => s.trim().toLowerCase();

const PlusIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);

const CheckIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

/**
 * A quiet, in-brand follow toggle. Monochrome until followed; amber only when
 * active (design-system: "color is earned through action"). Self-discovers
 * whether `(kind, value)` is already followed via getFollows().
 */
export function FollowButton({
  kind,
  value,
  label = "Follow",
  className,
  onToggle,
}: FollowButtonProps) {
  const [following, setFollowing] = useState(false);
  const [followId, setFollowId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  // Reflect existing follow state on mount (and whenever the target changes).
  useEffect(() => {
    let alive = true;
    getFollows()
      .then((follows: FollowItem[]) => {
        if (!alive) return;
        const match = follows.find(
          (f) => f.kind === kind && norm(f.value) === norm(value)
        );
        setFollowing(!!match);
        setFollowId(match ? match.id : null);
      })
      .catch(() => {
        /* offline — leave as unfollowed; the toggle still works */
      });
    return () => {
      alive = false;
    };
  }, [kind, value]);

  async function toggle() {
    if (busy) return;
    setBusy(true);
    if (following) {
      // Optimistic unfollow, roll back on failure.
      const prevId = followId;
      setFollowing(false);
      setFollowId(null);
      try {
        if (prevId != null) await removeFollow(prevId);
        onToggle?.(false);
      } catch {
        setFollowing(true);
        setFollowId(prevId);
      } finally {
        setBusy(false);
      }
    } else {
      // Optimistic follow, roll back on failure.
      setFollowing(true);
      try {
        const created = await addFollow(kind, value.trim());
        setFollowId(created.id);
        onToggle?.(true);
      } catch {
        setFollowing(false);
      } finally {
        setBusy(false);
      }
    }
  }

  return (
    <motion.button
      type="button"
      whileTap={{ scale: 0.96 }}
      transition={{ duration: 0.1 }}
      onClick={toggle}
      disabled={busy}
      aria-pressed={following}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-mono whitespace-nowrap",
        "transition-colors duration-[var(--duration-short)]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
        "disabled:opacity-60 disabled:pointer-events-none",
        following
          ? "border border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)]"
          : "border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:border-[var(--text-muted)]",
        className
      )}
    >
      {following ? <CheckIcon /> : <PlusIcon />}
      <span>{following ? "Following" : label}</span>
    </motion.button>
  );
}
