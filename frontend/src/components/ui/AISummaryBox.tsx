"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

type Tab = "summary" | "key-facts" | "5ws";

interface AISummaryBoxProps {
  summary: string | null;
  coherence?: number;
  className?: string;
}

const tabs: { id: Tab; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "key-facts", label: "Key Facts" },
  { id: "5ws", label: "5Ws" },
];

export function AISummaryBox({
  summary,
  coherence,
  className,
}: AISummaryBoxProps) {
  const [activeTab, setActiveTab] = useState<Tab>("summary");
  const isLow = coherence !== undefined && coherence < 0.6;

  return (
    <div
      className={cn(
        "rounded-[var(--radius-lg)] glass-light overflow-hidden",
        className
      )}
    >
      {/* Tab bar */}
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

      {/* Tab content */}
      <div className="p-4 min-h-[120px]">
        <AnimatePresence mode="wait">
          {activeTab === "summary" && (
            <motion.div
              key="summary"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
            >
              {summary ? (
                <p
                  className={cn(
                    "text-small text-[var(--text-secondary)] leading-relaxed",
                    isLow && "tracking-[0.5px]"
                  )}
                >
                  {summary}
                </p>
              ) : (
                <p className="text-small text-[var(--text-muted)] italic">
                  AI analysis unavailable
                </p>
              )}
            </motion.div>
          )}

          {activeTab === "key-facts" && (
            <motion.div
              key="key-facts"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="flex flex-col items-center justify-center py-4"
            >
              <div className="w-10 h-10 rounded-full bg-[var(--accent-subtle)] flex items-center justify-center mb-3">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <line x1="10" y1="9" x2="8" y2="9" />
                </svg>
              </div>
              <p className="text-small text-[var(--text-muted)]">
                Coming soon
              </p>
              <p className="text-mono text-[var(--text-ghost)] mt-1">
                Extracted key facts from all sources
              </p>
            </motion.div>
          )}

          {activeTab === "5ws" && (
            <motion.div
              key="5ws"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="flex flex-col items-center justify-center py-4"
            >
              <div className="w-10 h-10 rounded-full bg-[var(--accent-subtle)] flex items-center justify-center mb-3">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="12" cy="12" r="10" />
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <p className="text-small text-[var(--text-muted)]">
                Coming soon
              </p>
              <p className="text-mono text-[var(--text-ghost)] mt-1">
                Who, What, When, Where, Why
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Disclaimer */}
        {activeTab === "summary" && summary && (
          <p className="text-mono text-[var(--text-ghost)] mt-3 text-[10px]">
            AI-generated &middot; may contain errors &middot; verify with
            sources below
          </p>
        )}
      </div>
    </div>
  );
}
