"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { Badge } from "@/components/ui/Badge";
import { useTheme } from "@/components/ThemeProvider";
import {
  getSettings,
  getStats,
  updateSettings,
  testApiKey,
  type UserSettings,
  type KeyTestResult,
  type StatsResponse,
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
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<KeyTestResult | null>(null);

  // Local preferences (persisted to localStorage)
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("newslens-topics");
      return stored ? new Set(JSON.parse(stored)) : new Set(defaultTopics);
    }
    return new Set(defaultTopics);
  });

  const [stats, setStats] = useState<StatsResponse | null>(null);

  const { theme, setTheme } = useTheme();

  const fetchSettings = useCallback(async () => {
    try {
      setState("loading");
      const [settingsData, statsData] = await Promise.all([
        getSettings(),
        getStats().catch(() => null),
      ]);
      setSettings(settingsData);
      if (statsData) setStats(statsData);
      setState("idle");
    } catch {
      setError("Failed to load settings");
      setState("idle");
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  // Persist topic changes
  const toggleTopic = (topic: string) => {
    setSelectedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(topic)) {
        next.delete(topic);
      } else {
        next.add(topic);
      }
      localStorage.setItem("newslens-topics", JSON.stringify([...next]));
      return next;
    });
  };

  const handleSave = async () => {
    if (!keyInput.trim()) return;
    try {
      setState("saving");
      setError(null);
      setTestResult(null);
      const data = await updateSettings({ openai_api_key: keyInput.trim() });
      setSettings(data);
      setKeyInput("");
      setShowKey(false);
      setState("idle");
    } catch {
      setError("Failed to save API key");
      setState("editing");
    }
  };

  const handleRemove = async () => {
    try {
      setState("saving");
      setError(null);
      setTestResult(null);
      const data = await updateSettings({ openai_api_key: null });
      setSettings(data);
      setKeyInput("");
      setState("idle");
    } catch {
      setError("Failed to remove API key");
      setState("idle");
    }
  };

  const handleTest = async () => {
    try {
      setState("testing");
      setError(null);
      const result = await testApiKey();
      setTestResult(result);
      const data = await getSettings();
      setSettings(data);
      setState("idle");
    } catch {
      setTestResult({
        success: false,
        error: "Connection failed",
        models_available: 0,
      });
      setState("idle");
    }
  };

  const handleClearHistory = () => {
    localStorage.removeItem("newslens-topics");
    localStorage.removeItem("newslens-theme");
    setSelectedTopics(new Set(defaultTopics));
    setTheme("dark");
  };

  const isEditing = state === "editing" || keyInput.length > 0;

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
                  {defaultTopics.map((topic) => (
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
                          : "bg-[var(--surface-bg)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)]"
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>

          {/* AI Configuration */}
          <motion.div variants={fadeUp} className="mb-4">
            <Card variant="raised">
              <div className="p-3.5">
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-heading text-[var(--text-primary)]">
                    AI Configuration
                  </h2>
                  {settings?.has_openai_key && settings.openai_key_verified && (
                    <Badge variant="free" size="sm">
                      Active
                    </Badge>
                  )}
                </div>
                <p className="text-mono text-[var(--text-ghost)] mb-4">
                  OpenAI API key for embeddings and summaries
                </p>

                {/* Current key display */}
                {settings?.has_openai_key && !isEditing && (
                  <div>
                    <div className="flex items-center gap-2 py-2.5 px-3 rounded-[var(--radius-sm)] bg-[var(--surface-bg)]">
                      <span className="text-small text-[var(--text-muted)] tracking-wider flex-1">
                        {"••••••••••••" +
                          (settings.openai_key_last4 || "****")}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setState("editing")}
                      >
                        Change
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={handleRemove}
                        loading={state === "saving"}
                      >
                        Remove
                      </Button>
                    </div>

                    {/* Test connection */}
                    <div className="mt-3">
                      <Button
                        variant="secondary"
                        size="sm"
                        fullWidth
                        onClick={handleTest}
                        loading={state === "testing"}
                      >
                        Test Connection
                      </Button>
                    </div>

                    {/* Status */}
                    <div className="mt-3 flex items-center gap-2">
                      {testResult ? (
                        testResult.success ? (
                          <>
                            <span className="w-2 h-2 rounded-full bg-[var(--agree)]" />
                            <span className="text-mono text-[var(--agree)]">
                              Connected
                            </span>
                            <span className="text-mono text-[var(--text-ghost)]">
                              &middot; {testResult.models_available} models
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="w-2 h-2 rounded-full bg-[var(--dismiss)]" />
                            <span className="text-mono text-[var(--dismiss)]">
                              {testResult.error || "Test failed"}
                            </span>
                          </>
                        )
                      ) : settings.openai_key_verified ? (
                        <>
                          <span className="w-2 h-2 rounded-full bg-[var(--agree)]" />
                          <span className="text-mono text-[var(--agree)]">
                            Verified
                          </span>
                          {settings.openai_key_verified_at && (
                            <span className="text-mono text-[var(--text-ghost)]">
                              &middot;{" "}
                              {relativeTime(settings.openai_key_verified_at)}
                            </span>
                          )}
                        </>
                      ) : (
                        <>
                          <span className="w-2 h-2 rounded-full bg-[var(--text-ghost)]" />
                          <span className="text-mono text-[var(--text-ghost)]">
                            Not tested
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* Input field */}
                {(!settings?.has_openai_key || isEditing) && (
                  <div>
                    <Input
                      type={showKey ? "text" : "password"}
                      value={keyInput}
                      onChange={(e) => {
                        setKeyInput(e.target.value);
                        if (state !== "editing") setState("editing");
                      }}
                      placeholder="sk-..."
                      rightAction={
                        <button
                          type="button"
                          onClick={() => setShowKey(!showKey)}
                          className="text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
                          aria-label={showKey ? "Hide key" : "Show key"}
                        >
                          {showKey ? (
                            <svg
                              width="18"
                              height="18"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                              <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                              <line x1="1" y1="1" x2="23" y2="23" />
                            </svg>
                          ) : (
                            <svg
                              width="18"
                              height="18"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                          )}
                        </button>
                      }
                    />
                    <div className="flex gap-2 mt-3">
                      <Button
                        variant="primary"
                        size="md"
                        fullWidth
                        onClick={handleSave}
                        loading={state === "saving"}
                      >
                        Save Key
                      </Button>
                      {settings?.has_openai_key && (
                        <Button
                          variant="ghost"
                          size="md"
                          onClick={() => {
                            setKeyInput("");
                            setState("idle");
                          }}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  </div>
                )}

                {/* Error */}
                {error && (
                  <div className="mt-3 p-3 rounded-[var(--radius-sm)] bg-[var(--dismiss-muted)]">
                    <p className="text-mono text-[var(--dismiss)]">{error}</p>
                  </div>
                )}

                <p className="mt-4 text-mono text-[var(--text-ghost)]">
                  Your key is encrypted and stored securely.
                </p>
              </div>
            </Card>
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
