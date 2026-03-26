"use client";

import { motion } from "framer-motion";
import { Badge } from "@/components/ui/Badge";

interface SourceCardProps {
  sourceName: string;
  url: string;
  snippet: string | null;
  isFree: boolean;
  publishedAt?: string | null;
  index?: number;
}

function getInitial(name: string): string {
  return name.charAt(0).toUpperCase();
}

function getAvatarColor(name: string): string {
  const colors = [
    "var(--topic-tech)",
    "var(--topic-politics)",
    "var(--topic-business)",
    "var(--topic-science)",
    "var(--topic-sports)",
    "var(--topic-health)",
    "var(--topic-world)",
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

export function SourceCard({
  sourceName,
  url,
  snippet,
  isFree,
  publishedAt,
  index = 0,
}: SourceCardProps) {
  const avatarColor = getAvatarColor(sourceName);
  const borderColor = isFree ? "var(--agree)" : "var(--accent)";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: index * 0.04 }}
    >
      <div
        className="rounded-[var(--radius-md)] bg-[var(--surface-raised)] p-4 mb-3 border-l-[3px] transition-colors hover:bg-[var(--surface-hover)]"
        style={{ borderLeftColor: borderColor }}
      >
        {/* Header: avatar + source name + badge */}
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-[13px] font-semibold"
            style={{
              backgroundColor: `color-mix(in srgb, ${avatarColor} 15%, transparent)`,
              color: avatarColor,
            }}
          >
            {getInitial(sourceName)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-small font-semibold text-[var(--text-primary)] truncate">
                {sourceName}
              </span>
              <Badge variant={isFree ? "free" : "paywall"} size="sm">
                {isFree ? "Free" : "Paywall"}
              </Badge>
            </div>
            {publishedAt && (
              <span className="text-mono text-[var(--text-ghost)]">
                {new Date(publishedAt).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })}
              </span>
            )}
          </div>
        </div>

        {/* Excerpt */}
        {snippet && (
          <p className="text-small text-[var(--text-secondary)] mt-3 line-clamp-3 leading-relaxed">
            {snippet}
          </p>
        )}

        {/* Read link — full width button */}
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex items-center justify-center gap-2 w-full py-2.5 rounded-[var(--radius-sm)] bg-[var(--surface-bg)] text-small text-[var(--text-secondary)] font-medium transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        >
          Read full article
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="7" y1="17" x2="17" y2="7" />
            <polyline points="7 7 17 7 17 17" />
          </svg>
        </a>
      </div>
    </motion.div>
  );
}
