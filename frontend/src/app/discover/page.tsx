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
  type DiscoverCard as DiscoverCardType,
} from "@/lib/api";

type PageState = "loading" | "swiping" | "empty" | "error";

const PRE_FETCH_THRESHOLD = 5;

export default function DiscoverPage() {
  const [state, setState] = useState<PageState>("loading");
  const [deck, setDeck] = useState<DiscoverCardType[]>([]);
  const [totalSwiped, setTotalSwiped] = useState(0);
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

      setDeck((prev) => prev.slice(1));
      setTotalSwiped((prev) => prev + 1);

      recordSwipe(card.article_id, direction).catch(() => {});

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

      if (deck.length <= 1) {
        setState("empty");
      }
    },
    [deck]
  );

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
  const showAffordance = totalSwiped < 3;

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
          {/* Card stack */}
          <div
            className="relative w-full"
            style={{ height: "min(360px, calc(100dvh - 240px))" }}
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
                />
              ))}
            </AnimatePresence>
          </div>

          {/* Progress bar */}
          <div className="w-full max-w-[180px] mt-3">
            <div className="h-[2px] bg-[var(--surface-raised)] rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-[var(--accent)] rounded-full"
                initial={{ width: "100%" }}
                animate={{
                  width: `${Math.max(5, (deck.length / (deck.length + totalSwiped)) * 100)}%`,
                }}
                transition={{ duration: 0.3 }}
              />
            </div>
            <p className="text-mono text-[var(--text-ghost)] text-center mt-2">
              {deck.length} stories left
            </p>
          </div>

          {/* Swipe affordance hints — fade after 3 swipes */}
          <AnimatePresence>
            {showAffordance && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="flex items-center justify-center gap-5 mt-2"
              >
                <div className="flex flex-col items-center gap-1">
                  <div className="w-8 h-8 rounded-full bg-[var(--dismiss-muted)] flex items-center justify-center">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--dismiss)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </div>
                  <span className="text-[10px] text-[var(--text-ghost)]">Not interested</span>
                </div>
                <div className="flex flex-col items-center gap-1">
                  <div className="w-8 h-8 rounded-full bg-[var(--drill-muted)] flex items-center justify-center">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--drill)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="12" y1="19" x2="12" y2="5" /><polyline points="5 12 12 5 19 12" />
                    </svg>
                  </div>
                  <span className="text-[10px] text-[var(--text-ghost)]">Deep dive</span>
                </div>
                <div className="flex flex-col items-center gap-1">
                  <div className="w-8 h-8 rounded-full bg-[var(--agree-muted)] flex items-center justify-center">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--agree)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                  <span className="text-[10px] text-[var(--text-ghost)]">More like this</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
