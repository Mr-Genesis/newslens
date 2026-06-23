"use client";

import { useEffect, useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { getClusterAnalysis, type AnalysisLens, type LensResult } from "@/lib/api";

type Tab = "summary" | "key-facts" | "5ws";

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
];

const Disclaimer = () => (
  <p className="text-mono text-[var(--text-ghost)] mt-3 text-[10px]">
    AI-generated &middot; may contain errors &middot; verify with sources below
  </p>
);

export function AISummaryBox({ summary, coherence, clusterId, className }: AISummaryBoxProps) {
  const [activeTab, setActiveTab] = useState<Tab>("summary");
  const [cache, setCache] = useState<Record<string, LensResult | "loading">>({});
  const isLow = coherence !== undefined && coherence < 0.6;

  useEffect(() => {
    const lens = tabs.find((t) => t.id === activeTab)?.lens;
    if (!lens || !clusterId || cache[lens]) return;
    setCache((p) => ({ ...p, [lens]: "loading" }));
    getClusterAnalysis(clusterId, lens)
      .then((r) => setCache((p) => ({ ...p, [lens]: r })))
      .catch(() => setCache((p) => ({ ...p, [lens]: { unavailable: true } })));
  }, [activeTab, clusterId, cache]);

  const renderLens = (lens: AnalysisLens, body: (r: LensResult) => React.ReactNode) => {
    const state = cache[lens];
    if (!clusterId) return <Unavailable msg="Open a story to see analysis." />;
    if (state === "loading" || state === undefined)
      return <div className="skeleton h-16 w-full" />;
    if (state.unavailable) return <Unavailable />;
    return (
      <>
        {body(state)}
        <Disclaimer />
      </>
    );
  };

  return (
    <div className={cn("rounded-[var(--radius-lg)] glass-light overflow-hidden", className)}>
      <div className="flex border-b border-[var(--glass-border)]">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "relative flex-1 py-3 text-center text-[11px] font-medium uppercase tracking-wide transition-colors",
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
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function Unavailable({ msg }: { msg?: string }) {
  return (
    <p className="text-small text-[var(--text-muted)] italic">
      {msg ?? "AI analysis unavailable — add an API key in Settings."}
    </p>
  );
}
