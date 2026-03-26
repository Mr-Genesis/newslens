"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

const tabs = [
  {
    label: "Today",
    href: "/",
    icon: (active: boolean) => (
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        {!active && <polyline points="9 22 9 12 15 12 15 22" />}
      </svg>
    ),
  },
  {
    label: "Discover",
    href: "/discover",
    icon: (active: boolean) => (
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="10" />
        <polygon
          points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"
          fill={active ? "var(--bg)" : "none"}
          stroke={active ? "var(--bg)" : "currentColor"}
        />
      </svg>
    ),
  },
  {
    label: "Saved",
    href: "/saved",
    icon: (active: boolean) => (
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    label: "Profile",
    href: "/settings",
    icon: (active: boolean) => (
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    ),
  },
] as const;

export function BottomTabBar() {
  const pathname = usePathname();
  const isDeepDive = pathname.startsWith("/story");

  // Hide tab bar on deep dive pages
  if (isDeepDive) return null;

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  const activeIndex = tabs.findIndex((t) => isActive(t.href));

  return (
    <nav
      className={cn(
        "fixed bottom-0 left-0 right-0 z-50",
        "bg-[var(--bg)] border-t border-[var(--border)]",
        "pb-[var(--safe-bottom)]"
      )}
      style={{ WebkitBackfaceVisibility: "hidden" }}
    >
      <div className="relative flex items-center justify-around h-[var(--tab-bar-height)]">
        {/* Animated active indicator */}
        {activeIndex >= 0 && (
          <motion.div
            layoutId="tab-indicator"
            className="absolute top-0 h-[2px] bg-[var(--accent)] rounded-full"
            style={{ width: `${100 / tabs.length}%` }}
            animate={{ left: `${(activeIndex * 100) / tabs.length}%` }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
          />
        )}

        {tabs.map((tab) => {
          const active = isActive(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "flex flex-col items-center justify-center gap-0.5 flex-1 h-full",
                "transition-colors duration-[var(--duration-short)]",
                active
                  ? "text-[var(--accent)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              )}
            >
              {tab.icon(active)}
              <span
                className={cn(
                  "text-[10px] font-medium",
                  active && "font-semibold"
                )}
              >
                {tab.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
