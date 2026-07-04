"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { Badge } from "@/components/ui/Badge";
import { useTheme } from "@/components/ThemeProvider";
import { ProfileFields } from "@/components/ProfileFields";
import { ModelProviderCard } from "@/components/ModelProviderCard";
import { AccountCard } from "@/components/AccountCard";
import {
  getStats,
  getTopics,
  updateProfile,
  type StatsResponse,
  type Topic,
} from "@/lib/api";
import { relativeTime } from "@/lib/utils";

type PageState = "loading" | "idle" | "editing" | "saving" | "testing";

const defaultTopics = [
  "Technology",
  "Politics",
  "Business",
  "Science",
  "Sports",
  "Health",
  "World",
  "Entertainment",
];

function getGreetingName(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

const stagger = {
  animate: {
    transition: { staggerChildren: 0.06 },
  },
};

const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
};

export default function ProfilePage() {
  const [state, setState] = useState<PageState>("loading");

  // Local preferences (persisted to localStorage)
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("newslens-topics");
      return stored ? new Set(JSON.parse(stored)) : new Set(defaultTopics);
    }
    return new Set(defaultTopics);
  });

  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);

  const { theme, setTheme } = useTheme();

  const fetchSettings = useCallback(async () => {
    try {
      setState("loading");
      const [statsData, topicsData] = await Promise.all([
        getStats().catch(() => null),
        getTopics().catch(() => null),
      ]);
      if (statsData) setStats(statsData);
      if (topicsData) setTopics(topicsData.your_topics);
      setState("idle");
    } catch {
      setState("idle");
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  // Persist topic changes — locally (instant) and to the backend (so the feed reflects them)
  const toggleTopic = (topic: string) => {
    setSelectedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(topic)) {
        next.delete(topic);
      } else {
        next.add(topic);
      }
      const interests = [...next];
      localStorage.setItem("newslens-topics", JSON.stringify(interests));
      // Fire-and-forget: persist to profile so topic changes affect the feed.
      updateProfile({ interests }).catch(() => {
        /* offline / transient — local state already updated */
      });
      return next;
    });
  };

  const handleClearHistory = () => {
    localStorage.removeItem("newslens-topics");
    localStorage.removeItem("newslens-theme");
    setSelectedTopics(new Set(defaultTopics));
    setTheme("dark");
  };

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)]">
      {/* Loading */}
      {state === "loading" && (
        <div className="pt-6 space-y-4">
          <div className="skeleton h-16 w-16 rounded-full" />
          <div className="skeleton h-7 w-48" />
          <div className="skeleton h-5 w-32" />
          <div className="skeleton h-[200px] w-full rounded-[var(--radius-lg)]" />
        </div>
      )}

      {state !== "loading" && (
        <motion.div variants={stagger} initial="initial" animate="animate">
          {/* Profile header */}
          <motion.div variants={fadeUp} className="pt-3 pb-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-[var(--accent-subtle)] flex items-center justify-center">
                <svg
                  width="28"
                  height="28"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </div>
              <div>
                <h1 className="text-title text-[var(--text-primary)]">
                  {getGreetingName()}
                </h1>
                <p className="text-small text-[var(--text-muted)]">
                  NewsLens Reader
                </p>
              </div>
            </div>
          </motion.div>

          {/* Reading Stats */}
          {stats && (
            <motion.div variants={fadeUp} className="mb-4">
              <Card variant="raised">
                <div className="p-3.5">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <p className="text-title text-[var(--accent)]">
                        {stats.articles_read}
                      </p>
                      <p className="text-mono text-[var(--text-ghost)] mt-0.5">
                        Read
                      </p>
                    </div>
                    <div>
                      <p className="text-title text-[var(--accent)]">
                        {stats.stories_saved}
                      </p>
                      <p className="text-mono text-[var(--text-ghost)] mt-0.5">
                        Saved
                      </p>
                    </div>
                    <div>
                      <p className="text-title text-[var(--accent)]">
                        {stats.topics_explored}
                      </p>
                      <p className="text-mono text-[var(--text-ghost)] mt-0.5">
                        Topics
                      </p>
                    </div>
                  </div>
                </div>
              </Card>
            </motion.div>
          )}

          {/* Account — sign-in entry point (the /login page is unreachable without this) */}
          <motion.div variants={fadeUp} className="mb-4">
            <AccountCard />
          </motion.div>

          {/* Profile + Gemini key (v2) */}
          <motion.div variants={fadeUp} className="flex flex-col gap-4 mb-4">
            <ProfileFields />
          </motion.div>

          {/* Your Topics */}
          <motion.div variants={fadeUp} className="mb-4">
            <Card variant="raised">
              <div className="p-3.5">
                <h2 className="text-heading text-[var(--text-primary)] mb-1">
                  Your Topics
                </h2>
                <p className="text-mono text-[var(--text-ghost)] mb-4">
                  Toggle topics to customize your briefing
                </p>
                <div className="flex flex-wrap gap-2">
                  {(topics.length > 0
                    ? topics.map((t) => t.name)
                    : defaultTopics
                  ).map((topic) => (
                    <Chip
                      key={topic}
                      selected={selectedTopics.has(topic)}
                      onClick={() => toggleTopic(topic)}
                    >
                      {topic}
                    </Chip>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>

          {/* Following — manage standing follows */}
          <motion.div variants={fadeUp} className="mb-4">
            <Card variant="raised">
              <Link
                href="/following"
                className="flex items-center justify-between p-3.5 group"
              >
                <div>
                  <h2 className="text-heading text-[var(--text-primary)] mb-1">
                    Following
                  </h2>
                  <p className="text-mono text-[var(--text-ghost)]">
                    Topics, people and saved searches you track
                  </p>
                </div>
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="shrink-0 text-[var(--text-muted)] group-hover:text-[var(--text-secondary)] transition-colors"
                >
                  <path d="M9 18l6-6-6-6" />
                </svg>
              </Link>
            </Card>
          </motion.div>

          {/* Appearance */}
          <motion.div variants={fadeUp} className="mb-4">
            <Card variant="raised">
              <div className="p-3.5">
                <h2 className="text-heading text-[var(--text-primary)] mb-1">
                  Appearance
                </h2>
                <p className="text-mono text-[var(--text-ghost)] mb-4">
                  Theme preference
                </p>
                <div className="flex gap-2">
                  {(["dark", "light", "auto"] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setTheme(t)}
                      className={`flex-1 py-2.5 rounded-[var(--radius-sm)] text-small font-medium capitalize transition-colors ${
                        theme === t
                          ? "bg-[var(--accent)] text-[var(--gray-950)]"
                          : "bg-[var(--surface)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)]"
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>

          {/* Wave E: provider + model + Anthropic key */}
          <motion.div variants={fadeUp} className="mb-4">
            <ModelProviderCard />
          </motion.div>


          {/* Data & Privacy */}
          <motion.div variants={fadeUp} className="mb-4">
            <Card variant="raised">
              <div className="p-3.5">
                <h2 className="text-heading text-[var(--text-primary)] mb-1">
                  Data & Privacy
                </h2>
                <p className="text-mono text-[var(--text-ghost)] mb-4">
                  Manage your local data
                </p>
                <Button
                  variant="secondary"
                  size="md"
                  fullWidth
                  onClick={handleClearHistory}
                >
                  Reset Preferences
                </Button>
              </div>
            </Card>
          </motion.div>

          {/* About */}
          <motion.div variants={fadeUp} className="mb-4">
            <Card variant="raised">
              <div className="p-3.5">
                <h2 className="text-heading text-[var(--text-primary)] mb-3">
                  About
                </h2>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-small text-[var(--text-muted)]">
                      Version
                    </span>
                    <span className="text-mono text-[var(--text-ghost)]">
                      0.1.0-alpha
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-small text-[var(--text-muted)]">
                      Built with
                    </span>
                    <span className="text-mono text-[var(--text-ghost)]">
                      Next.js + FastAPI
                    </span>
                  </div>
                </div>
              </div>
            </Card>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}
