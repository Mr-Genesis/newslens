"use client";

import { motion } from "framer-motion";
import { postFeedback } from "@/lib/api";
import { useState } from "react";

interface StoryActionBarProps {
  articleId: number;
}

export function StoryActionBar({ articleId }: StoryActionBarProps) {
  const [savedState, setSavedState] = useState<
    "idle" | "saving" | "saved"
  >("idle");

  const handleSave = async () => {
    if (savedState === "saved") return;
    setSavedState("saving");
    try {
      await postFeedback(articleId, "save");
      setSavedState("saved");
    } catch {
      setSavedState("idle");
    }
  };

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({
        title: "NewsLens Story",
        url: window.location.href,
      });
    } else {
      navigator.clipboard.writeText(window.location.href);
    }
    postFeedback(articleId, "share").catch(() => {});
  };

  const handleLess = () => {
    postFeedback(articleId, "less").catch(() => {});
  };

  const actions = [
    {
      label: savedState === "saved" ? "Saved" : "Save",
      onClick: handleSave,
      icon: (
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill={savedState === "saved" ? "var(--accent)" : "none"}
          stroke={
            savedState === "saved" ? "var(--accent)" : "var(--text-secondary)"
          }
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
        </svg>
      ),
    },
    {
      label: "Share",
      onClick: handleShare,
      icon: (
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--text-secondary)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="18" cy="5" r="3" />
          <circle cx="6" cy="12" r="3" />
          <circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
      ),
    },
    {
      label: "Less",
      onClick: handleLess,
      icon: (
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--text-secondary)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
        </svg>
      ),
    },
  ];

  return (
    <div className="fixed bottom-0 left-0 right-0 z-30">
      <div className="mx-auto max-w-[640px] px-[var(--space-md)] pb-[calc(var(--safe-bottom)+var(--space-sm))]">
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.3, type: "spring", stiffness: 300, damping: 25 }}
          className="glass rounded-full px-2 py-1.5 flex items-center justify-around"
        >
          {actions.map((action) => (
            <motion.button
              key={action.label}
              whileTap={{ scale: 0.9 }}
              onClick={action.onClick}
              className="flex flex-col items-center gap-0.5 px-5 py-1.5 rounded-full transition-colors hover:bg-[var(--surface-hover)]"
            >
              {action.icon}
              <span className="text-[10px] text-[var(--text-ghost)] font-medium">
                {action.label}
              </span>
            </motion.button>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
