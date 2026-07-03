"use client";

import { useEffect, useState, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { DiscoverCard } from "@/components/DiscoverCard";
import { Button } from "@/components/ui/Button";
import { DiscoverCardSkeleton } from "@/components/ui/Skeleton";
import {
  getDiscoverDeck,
  recordSwipe,
  getTopicCards,
  addFollow,
  type DiscoverCard as DiscoverCardType,
} from "@/lib/api";

type PageState = "loading" | "swiping" | "empty" | "error";

const PRE_FETCH_THRESHOLD = 5;

export default function DiscoverPage() {
  const [state, setState] = useState<PageState>("loading");
  const [deck, setDeck] = useState<DiscoverCardType[]>([]);
  const [totalSwiped, setTotalSwiped] = useState(0);
  const [batchTotal, setBatchTotal] = useState(0); // frozen per batch — counter never inflates on prefetch
  const [history, setHistory] = useState<DiscoverCardType[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState(false);

  const fetchDeck = useCallback(async () => {
    try {
      setState("loading");
      setError(null);
      const cards = await getDiscoverDeck();

      if (!cards || cards.length === 0) {
        setState("empty");
        return;
      }

      setDeck(cards);
      setBatchTotal(cards.length); // freeze the counter denominator for this batch
      setTotalSwiped(0);
      setState("swiping");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deck");
      setState("error");
    }
  }, []);

  useEffect(() => {
    fetchDeck();
  }, [fetchDeck]);

  // Pre-fetch when deck runs low
  useEffect(() => {
    if (
      deck.length <= PRE_FETCH_THRESHOLD &&
      deck.length > 0 &&
      !isFetching &&
      state === "swiping"
    ) {
      setIsFetching(true);
      getDiscoverDeck()
        .then((newCards) => {
          if (newCards && newCards.length > 0) {
            setDeck((prev) => [...prev, ...newCards]);
          }
        })
        .catch(() => {})
        .finally(() => setIsFetching(false));
    }
  }, [deck.length, isFetching, state]);

  const handleSwipe = useCallback(
    async (direction: "right" | "left" | "up") => {
      const card = deck[0];
      if (!card) return;

      setHistory((prev) => [...prev, card]);
      setDeck((prev) => prev.slice(1));
      setTotalSwiped((prev) => prev + 1);

      recordSwipe(card.article_id, direction).catch(() => {});

      // #83: a right swipe on a gated (research/expert) card also follows the source — the
      // frictionless opt-in. Idempotent server-side, so a repeat swipe is harmless.
      if (direction === "right" && card.is_gated && card.source_id != null) {
        addFollow("source", String(card.source_id)).catch(() => {});
      }

      if (direction === "up" && card.topic_id > 0) {
        try {
          const topicCards = await getTopicCards(card.topic_id);
          if (topicCards && topicCards.length > 0) {
            setDeck((prev) => [...topicCards, ...prev]);
          }
        } catch {
          // Silent failure
        }
      }

      if (direction === "right" && card.topic_id > 0) {
        try {
          const topicCards = await getTopicCards(card.topic_id);
          if (topicCards && topicCards.length > 0) {
            setDeck((prev) => [...prev, ...topicCards]);
          }
        } catch {
          // Silent failure
        }
      }

    },
    [deck]
  );

  // Deck exhausted → "caught up". An effect (not a stale-closure check inside handleSwipe)
  // so async topic-card refills are respected and there's no premature empty-state flash.
  useEffect(() => {
    if (state === "swiping" && deck.length === 0) setState("empty");
  }, [deck.length, state]);

  const handleUndo = useCallback(() => {
    setHistory((h) => {
      if (h.length === 0) return h;
      const last = h[h.length - 1];
      setDeck((d) => [last, ...d]);
      setTotalSwiped((n) => Math.max(0, n - 1));
      setState("swiping");
      return h.slice(0, -1);
    });
  }, []);

  // Keyboard support
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (state !== "swiping" || deck.length === 0) return;
      switch (e.key) {
        case "ArrowRight":
          handleSwipe("right");
          break;
        case "ArrowLeft":
          handleSwipe("left");
          break;
        case "ArrowUp":
          handleSwipe("up");
          break;
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [state, deck.length, handleSwipe]);

  const visibleCards = deck.slice(0, 3);

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)]">
      {/* Loading */}
      {state === "loading" && (
        <div className="pt-6">
          <DiscoverCardSkeleton />
        </div>
      )}

      {/* Error */}
      {state === "error" && (
        <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
          <div className="w-12 h-12 rounded-full bg-[var(--dismiss-muted)] flex items-center justify-center mb-4">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--dismiss)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <p className="text-heading text-[var(--text-primary)]">
            Unable to load stories
          </p>
          {error && <p className="text-mono text-[var(--dismiss)] mt-2">{error}</p>}
          <Button variant="secondary" onClick={fetchDeck} className="mt-4">
            Try again
          </Button>
        </div>
      )}

      {/* Empty */}
      {state === "empty" && (
        <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
          <motion.div
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
            className="w-12 h-12 text-[var(--text-ghost)] mb-4"
          >
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
            </svg>
          </motion.div>
          <p className="text-heading text-[var(--text-primary)]">
            You&apos;re all caught up
          </p>
          <p className="text-small text-[var(--text-muted)] mt-2">
            Come back in an hour for fresh stories
          </p>
          <Button variant="secondary" onClick={fetchDeck} className="mt-4">
            Load more stories
          </Button>
        </div>
      )}

      {/* Swiping: card stack */}
      {state === "swiping" && (
        <div className="flex flex-col items-center pt-2">
          {/* Header */}
          <div className="w-full mb-3 flex items-end justify-between">
            <div>
              <h1 className="text-hero text-[var(--text-primary)]">Discover</h1>
              <p className="text-mono text-[var(--text-muted)] mt-1">SWIPE TO TRIAGE</p>
            </div>
            <p className="text-mono text-[var(--text-ghost)]">
              {Math.min(totalSwiped + 1, batchTotal)} / {batchTotal}
            </p>
          </div>

          {/* Card stack — the container is the single source of height truth; cards fill it
              (inset-0). 344 ≈ page chrome (top 48 + header 84 + gap 24 + buttons 92 + bottom 72 + slack). */}
          <div
            className="discover-stack relative w-full"
            style={{ height: "clamp(360px, calc(100dvh - 344px), 560px)" }}
            role="group"
            aria-label="Discover card deck"
          >
            <AnimatePresence>
              {visibleCards.map((card, index) => (
                <DiscoverCard
                  key={card.id}
                  card={card}
                  onSwipe={handleSwipe}
                  isTop={index === 0}
                  stackIndex={index}
                  // #104: pass viewport dims so commit thresholds scale with orientation.
                  viewportWidth={typeof window !== "undefined" ? window.innerWidth : undefined}
                  cardHeight={typeof window !== "undefined" ? window.innerHeight : undefined}
                />
              ))}
            </AnimatePresence>
          </div>

          {/* Action buttons — Skip / Undo / Save */}
          <div className="flex items-center justify-center gap-6 mt-6">
            <div className="flex flex-col items-center gap-1.5">
              <motion.button
                whileTap={{ scale: 0.92 }}
                onClick={() => handleSwipe("left")}
                aria-label="Skip"
                className="w-12 h-12 rounded-full bg-[var(--surface-raised)] border border-[var(--border)] flex items-center justify-center text-[var(--text-secondary)]"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
              </motion.button>
              <span className="text-mono text-[10px] text-[var(--text-ghost)]">SKIP</span>
            </div>
            <div className="flex flex-col items-center gap-1.5">
              <motion.button
                whileTap={{ scale: 0.92 }}
                onClick={handleUndo}
                disabled={history.length === 0}
                aria-label="Undo last"
                className="w-11 h-11 rounded-full bg-[var(--surface-raised)] border border-[var(--border)] flex items-center justify-center text-[var(--text-muted)] disabled:opacity-40"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" /></svg>
              </motion.button>
              <span className="text-mono text-[10px] text-[var(--text-ghost)]">UNDO</span>
            </div>
            <div className="flex flex-col items-center gap-1.5">
              <motion.button
                whileTap={{ scale: 0.92 }}
                onClick={() => handleSwipe("right")}
                aria-label="Save"
                className="w-16 h-16 rounded-full bg-[var(--accent)] text-[var(--bg)] flex items-center justify-center shadow-[var(--shadow-md)]"
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" /></svg>
              </motion.button>
              <span className="text-mono text-[10px] text-[var(--accent)]">SAVE</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
