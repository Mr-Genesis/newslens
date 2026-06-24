"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { StoryCard } from "@/components/StoryCard";
import { HeroStoryCard } from "@/components/HeroStoryCard";
import { Chip } from "@/components/ui/Chip";
import { FollowButton } from "@/components/ui/FollowButton";
import { Button } from "@/components/ui/Button";
import { StoryCardSkeleton } from "@/components/ui/Skeleton";
import { DailyTriviaCard } from "@/components/ui/DailyTriviaCard";
import { PersonalizeBanner } from "@/components/ui/PersonalizeBanner";
import { LaunchScreen } from "@/components/LaunchScreen";
import { getBriefing, type Briefing, type BriefingStory } from "@/lib/api";
import { isStale } from "@/lib/utils";
import { cn } from "@/lib/utils";

type PageState = "loading" | "success" | "error" | "empty" | "refreshing";

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function formatDate(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

const staggerContainer = {
  animate: {
    transition: { staggerChildren: 0.04 },
  },
};

export default function BriefingPage() {
  const [state, setState] = useState<PageState>("loading");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string>("All");
  const [rechecking, setRechecking] = useState(false);
  const router = useRouter();

  // First-run: send new users through the intro (once per browser).
  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("newslens-onboarded")) {
      router.replace("/welcome");
    }
  }, [router]);

  const fetchBriefing = useCallback(async (isRefresh = false) => {
    try {
      setState(isRefresh ? "refreshing" : "loading");
      setError(null);
      const data = await getBriefing();

      if (!data.stories || data.stories.length === 0) {
        setState("empty");
        return;
      }

      setBriefing(data);
      setState("success");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load briefing"
      );
      setState("error");
    }
  }, []);

  useEffect(() => {
    fetchBriefing();
  }, [fetchBriefing]);

  // Silent cold-start re-check: keeps the launch screen mounted (no "refreshing"
  // flash) and only flips to success once stories arrive.
  const recheckBriefing = useCallback(async () => {
    setRechecking(true);
    try {
      const data = await getBriefing();
      if (data.stories && data.stories.length > 0) {
        setBriefing(data);
        setState("success");
      }
    } catch {
      /* still warming up — stay on the launch screen */
    } finally {
      setRechecking(false);
    }
  }, []);

  // While the first briefing is still warming up (empty), quietly re-check every
  // 20s so the launch screen advances to the feed on its own.
  useEffect(() => {
    if (state !== "empty") return;
    const id = setInterval(recheckBriefing, 20000);
    return () => clearInterval(id);
  }, [state, recheckBriefing]);

  // Get unique categories
  const categories = briefing
    ? [
        "All",
        ...Array.from(
          new Set(briefing.stories.map((s) => s.category || "General"))
        ),
      ]
    : [];

  // Filter stories by category
  const filteredStories =
    briefing?.stories.filter(
      (s) =>
        activeCategory === "All" ||
        (s.category || "General") === activeCategory
    ) || [];

  // Hero story is the first one (highest source count / importance)
  const heroStory = filteredStories[0];
  const remainingStories = filteredStories.slice(1);

  // Group remaining by category
  const grouped = remainingStories.reduce<Record<string, BriefingStory[]>>(
    (acc, story) => {
      const cat = story.category || "General";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(story);
      return acc;
    },
    {}
  );

  return (
    <PullToRefresh onRefresh={() => fetchBriefing(true)}>
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)]">
      {/* Greeting + Date */}
      {(state === "success" || state === "refreshing") && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="pt-4 pb-2"
        >
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-mono text-[var(--accent)] uppercase">
              {getGreeting()} &middot; {formatDate()}
            </p>
            {briefing && isStale(briefing.generated_at) && (
              <Badge variant="accent" size="md">
                Stale
              </Badge>
            )}
          </div>
        </motion.div>
      )}

      {/* Topic chips */}
      {(state === "success" || state === "refreshing") &&
        categories.length > 2 && (
          <div className="flex gap-2 overflow-x-auto no-scrollbar py-3 -mx-4 px-4">
            {categories.map((cat) => (
              <Chip
                key={cat}
                selected={activeCategory === cat}
                onClick={() => setActiveCategory(cat)}
              >
                {cat}
              </Chip>
            ))}
          </div>
        )}

      {/* Follow the topic you've filtered to — kept quiet until a topic is picked */}
      {(state === "success" || state === "refreshing") &&
        activeCategory !== "All" && (
          <div className="flex justify-end mb-2">
            <FollowButton
              key={activeCategory}
              kind="topic"
              value={activeCategory}
              label="Follow topic"
            />
          </div>
        )}

      {/* Loading state */}
      {state === "loading" && (
        <div className="pt-4">
          <div className="h-8 w-48 skeleton mb-4" />
          <div className="h-5 w-32 skeleton mb-6" />
          {[1, 2, 3, 4, 5].map((i) => (
            <StoryCardSkeleton key={i} />
          ))}
        </div>
      )}

      {/* Empty / first-run state — cold-start launch experience */}
      {state === "empty" && (
        <LaunchScreen onRetry={recheckBriefing} refreshing={rechecking} />
      )}

      {/* Error state */}
      {state === "error" && (
        <div className="flex flex-col items-center justify-center pt-[var(--space-3xl)] text-center">
          <div className="w-12 h-12 rounded-full bg-[var(--dismiss-muted)] flex items-center justify-center mb-4">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--dismiss)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <p className="text-heading text-[var(--text-primary)]">
            Couldn&apos;t load briefing
          </p>
          {error && (
            <p className="text-mono text-[var(--dismiss)] mt-2">{error}</p>
          )}
          <Button
            variant="secondary"
            size="md"
            onClick={() => fetchBriefing()}
            className="mt-4"
          >
            Try again
          </Button>
        </div>
      )}

      {/* Success: hero + categorized stories */}
      {(state === "success" || state === "refreshing") && (
        <motion.div
          className={cn(state === "refreshing" && "opacity-80")}
          variants={staggerContainer}
          initial="initial"
          animate="animate"
        >
          {/* Personalize impact lens (E3) — self-gates: only after first impact card */}
          <PersonalizeBanner />

          {/* Daily quiz (E8) — dismissible, returns each day */}
          <DailyTriviaCard />

          {/* Hero story */}
          {heroStory && (
            <div className="mb-4">
              <h2 className="text-category text-[var(--text-muted)] mb-2">
                TOP STORY
              </h2>
              <HeroStoryCard story={heroStory} />
            </div>
          )}

          {/* Categorized stories */}
          {activeCategory === "All"
            ? Object.entries(grouped).map(([category, stories]) => (
                <section key={category} className="mb-4">
                  <h2 className="text-category text-[var(--text-muted)] mb-2">
                    {category}
                  </h2>
                  {stories.map((story) => (
                    <StoryCard key={story.cluster_id} story={story} />
                  ))}
                </section>
              ))
            : remainingStories.map((story) => (
                <StoryCard key={story.cluster_id} story={story} />
              ))}

          {/* Refresh */}
          <div className="flex justify-center py-8">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => fetchBriefing(true)}
              loading={state === "refreshing"}
            >
              Refresh briefing
            </Button>
          </div>
        </motion.div>
      )}
    </div>
    </PullToRefresh>
  );
}

// Need Badge import for stale indicator
import { Badge } from "@/components/ui/Badge";
import { PullToRefresh } from "@/components/PullToRefresh";
