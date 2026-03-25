"use client";

import { useEffect, useState, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { NavBar } from "@/components/layout/NavBar";
import { DiscoverCard } from "@/components/DiscoverCard";
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
        .catch(() => {
          // Silent failure on pre-fetch
        })
        .finally(() => setIsFetching(false));
    }
  }, [deck.length, isFetching, state]);

  const handleSwipe = useCallback(
    async (direction: "right" | "left" | "up") => {
      const card = deck[0];
      if (!card) return;

      // Optimistic: remove card from deck
      setDeck((prev) => prev.slice(1));

      // Record swipe (fire and forget)
      recordSwipe(card.article_id, direction).catch(() => {});

      // Swipe up: insert topic cards at front
      if (direction === "up") {
        try {
          const topicCards = await getTopicCards(card.topic_id);
          if (topicCards && topicCards.length > 0) {
            setDeck((prev) => [...topicCards, ...prev]);
          }
        } catch {
          // Silent failure
        }
      }

      // Check if deck exhausted
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

  // Visible cards (top 3)
  const visibleCards = deck.slice(0, 3);

  return (
    <>
      <NavBar />
      <main className="flex-1 mx-auto max-w-[640px] w-full px-[var(--space-md)] pb-[var(--space-3xl)]">
        <div className="pt-[var(--space-lg)] pb-[var(--space-sm)]">
          <h1 className="text-hero text-[var(--text-primary)]">Discover</h1>
          <p className="text-mono text-[var(--text-ghost)] mt-1">
            Swipe right = more like this &middot; left = less &middot; up = deep dive
          </p>
        </div>

        {/* Loading */}
        {state === "loading" && (
          <div className="mt-[var(--space-lg)]">
            <DiscoverCardSkeleton />
          </div>
        )}

        {/* Error */}
        {state === "error" && (
          <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
            <p className="text-body text-[var(--text-secondary)]">
              Couldn&apos;t load discover deck
            </p>
            {error && (
              <p className="text-mono text-[var(--dismiss)] mt-2">{error}</p>
            )}
            <button
              onClick={fetchDeck}
              className="mt-4 px-4 py-2 rounded-[var(--radius-sm)] bg-[var(--surface-raised)] text-small text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Empty */}
        {state === "empty" && (
          <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
            <p className="text-body text-[var(--text-secondary)]">
              You&apos;re all caught up
            </p>
            <p className="text-small text-[var(--text-ghost)] mt-2">
              No more stories to discover right now.
            </p>
            <button
              onClick={fetchDeck}
              className="mt-4 px-4 py-2 rounded-[var(--radius-sm)] bg-[var(--surface-raised)] text-small text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
            >
              Refresh deck
            </button>
          </div>
        )}

        {/* Swiping: card stack */}
        {state === "swiping" && (
          <div className="relative mt-[var(--space-lg)] h-[380px]">
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

            {/* Deck counter */}
            <div className="absolute bottom-[-32px] left-0 right-0 text-center">
              <span className="text-mono text-[var(--text-ghost)]">
                {deck.length} cards remaining
              </span>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
