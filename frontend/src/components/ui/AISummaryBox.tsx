"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  getClusterAnalysis,
  getProfile,
  type AnalysisLens,
  type LensResult,
} from "@/lib/api";

type Tab = "summary" | "key-facts" | "5ws" | "for-you";

interface AISummaryBoxProps {
  summary: string | null;
  coherence?: number;
  clusterId?: number;
  className?: string;
}

const tabs: { id: Tab; label: string; lens?: AnalysisLens }[] = [
  { id: "summary", label: "Summary" },
  { id: "key-facts", label: "Key Facts", lens: "key_facts" },
  { id: "5ws", label: "5Ws", lens: "5ws" },
  { id: "for-you", label: "For You", lens: "profession" },
];

const Disclaimer = () => (
  <p className="text-mono text-[var(--text-ghost)] mt-3 text-[10px]">
    AI-generated &middot; may contain errors &middot; verify with sources below
  </p>
);

export function AISummaryBox({ summary, coherence, clusterId, className }: AISummaryBoxProps) {
  const [activeTab, setActiveTab] = useState<Tab>("summary");
  const [cache, setCache] = useState<Record<string, LensResult | "loading">>({});
  // null = still loading the profile; "" = profile loaded but profession unset.
  const [profession, setProfession] = useState<string | null>(null);
  const isLow = coherence !== undefined && coherence < 0.6;

  useEffect(() => {
    getProfile()
      .then((p) => setProfession(p.profession ?? ""))
      .catch(() => setProfession(""));
  }, []);

  useEffect(() => {
    const lens = tabs.find((t) => t.id === activeTab)?.lens;
    if (!lens || !clusterId || cache[lens]) return;
    // The profession lens needs a set profession — don't fetch until we have one.
    if (lens === "profession" && !profession) return;
    setCache((p) => ({ ...p, [lens]: "loading" }));
    getClusterAnalysis(clusterId, lens)
      .then((r) => setCache((p) => ({ ...p, [lens]: r })))
      .catch(() => setCache((p) => ({ ...p, [lens]: { unavailable: true } })));
  }, [activeTab, clusterId, cache, profession]);

  const renderLens = (lens: AnalysisLens, body: (r: LensResult) => React.ReactNode) => {
    const state = cache[lens];
    if (!clusterId) return <Unavailable msg="Open a story to see analysis." />;
    if (state === "loading" || state === undefined)
      return <div className="skeleton h-16 w-full" />;
    if (state.unavailable || state.error)
      return <Unavailable reason={state.reason ?? state.error} />;
    return (
      <>
        {body(state)}
        <Disclaimer />
      </>
    );
  };

  return (
    <div className={cn("rounded-[var(--radius-lg)] glass-light overflow-hidden", className)}>
      <div className="flex border-b border-[var(--glass-border)] overflow-x-auto no-scrollbar">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "relative flex-1 min-w-[72px] whitespace-nowrap py-3 text-center text-[11px] font-medium uppercase tracking-wide transition-colors",
              "font-[family-name:var(--font-jetbrains-mono)]",
              activeTab === tab.id
                ? "text-[var(--accent)]"
                : "text-[var(--text-ghost)] hover:text-[var(--text-muted)]"
            )}
          >
            {tab.label}
            {activeTab === tab.id && (
              <motion.div
                layoutId="ai-tab-indicator"
                className="absolute bottom-0 left-2 right-2 h-[2px] bg-[var(--accent)] rounded-full"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
          </button>
        ))}
      </div>

      <div className="p-4 min-h-[120px]">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
          >
            {activeTab === "summary" &&
              (summary ? (
                <>
                  <p
                    className={cn(
                      "text-small text-[var(--text-secondary)] leading-relaxed",
                      isLow && "tracking-[0.5px]"
                    )}
                  >
                    {summary}
                  </p>
                  <Disclaimer />
                </>
              ) : (
                <p className="text-small text-[var(--text-muted)] italic">
                  AI analysis unavailable
                </p>
              ))}

            {activeTab === "key-facts" &&
              renderLens("key_facts", (r) => {
                const facts = (r.facts as string[] | undefined) ?? [];
                return facts.length ? (
                  <ul className="space-y-2">
                    {facts.map((f, i) => (
                      <li key={i} className="flex gap-2 text-small text-[var(--text-secondary)]">
                        <span className="text-[var(--accent)] shrink-0">&bull;</span>
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Unavailable />
                );
              })}

            {activeTab === "5ws" &&
              renderLens("5ws", (r) => {
                const ws: [string, string][] = [
                  ["Who", r.who as string],
                  ["What", r.what as string],
                  ["When", r.when as string],
                  ["Where", r.where as string],
                  ["Why", r.why as string],
                ];
                return (
                  <dl className="space-y-2">
                    {ws.map(([k, v]) =>
                      v ? (
                        <div key={k} className="text-small">
                          <dt className="text-mono text-[var(--accent)] uppercase">{k}</dt>
                          <dd className="text-[var(--text-secondary)]">{v}</dd>
                        </div>
                      ) : null
                    )}
                  </dl>
                );
              })}

            {activeTab === "for-you" &&
              (profession === null ? (
                <div className="skeleton h-16 w-full" />
              ) : profession === "" ? (
                <Link
                  href="/settings"
                  className="block text-small text-[var(--accent)] hover:underline"
                >
                  Set your profession in Settings &rarr;
                </Link>
              ) : (
                renderLens("profession", (r) => {
                  const headline = typeof r.headline === "string" ? r.headline : null;
                  const points = Array.isArray(r.points) ? (r.points as string[]) : [];
                  const dims = Array.isArray(r.dimensions)
                    ? (r.dimensions as { label?: string; body?: string }[])
                    : [];
                  if (!headline && points.length === 0 && dims.length === 0) {
                    return <Unavailable />;
                  }
                  return (
                    <div className="space-y-3">
                      {headline && (
                        <p className="text-small text-[var(--text-secondary)] leading-relaxed">
                          {headline}
                        </p>
                      )}
                      {points.length > 0 && (
                        <ul className="space-y-2">
                          {points.map((p, i) => (
                            <li
                              key={i}
                              className="flex gap-2 text-small text-[var(--text-secondary)]"
                            >
                              <span className="text-[var(--accent)] shrink-0">&bull;</span>
                              <span>{p}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                      {dims.length > 0 && (
                        <dl className="space-y-2">
                          {dims.map((d, i) => (
                            <div key={i} className="text-small">
                              {d.label && (
                                <dt className="text-mono text-[var(--accent)] uppercase">
                                  {d.label}
                                </dt>
                              )}
                              {d.body && (
                                <dd className="text-[var(--text-secondary)]">{d.body}</dd>
                              )}
                            </div>
                          ))}
                        </dl>
                      )}
                    </div>
                  );
                })
              ))}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function Unavailable({ msg, reason }: { msg?: string; reason?: string }) {
  // Map the backend's failure reason to honest copy. The old catch-all told everyone to "add an
  // API key" even when the story simply wasn't clustered/processed yet — misleading when the
  // platform key is configured and working.
  const text =
    msg ??
    (reason === "no_llm_key"
      ? "AI analysis unavailable — add an API key in Settings."
      : reason === "llm_error"
        ? "AI analysis hit a temporary error — try again shortly."
        : reason === "profession_unset"
          ? "Set your profession in Settings to unlock this lens."
          : "Analysis isn't ready for this story yet — check back soon.");
  return <p className="text-small text-[var(--text-muted)] italic">{text}</p>;
}
