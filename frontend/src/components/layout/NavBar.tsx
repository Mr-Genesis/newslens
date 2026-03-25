"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const segments = [
  { label: "Briefing", href: "/" },
  { label: "Discover", href: "/discover" },
] as const;

export function NavBar() {
  const pathname = usePathname();

  // Deep Dive and Settings pages don't highlight any tab
  const isDeepDive = pathname.startsWith("/story/");
  const isSettings = pathname.startsWith("/settings");

  function isActive(href: string) {
    if (isDeepDive || isSettings) return false;
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <header className="sticky top-0 z-30 bg-[var(--bg)]">
      {/* Brand + segment bar */}
      <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)]">
        <div className="flex items-center justify-between h-12">
          {/* Logo */}
          <Link href="/" className="flex items-baseline gap-0 shrink-0">
            <span className="text-hero text-[var(--text-primary)] !text-[20px]">
              News
            </span>
            <span className="text-hero text-[var(--accent)] !text-[20px]">
              Lens
            </span>
          </Link>

          {/* Nav tabs + settings */}
          <div className="flex items-center gap-6">
            <nav className="flex items-center gap-6">
              {segments.map((seg) => (
                <Link
                  key={seg.href}
                  href={seg.href}
                  className={cn(
                    "text-small font-medium transition-colors duration-[var(--duration-short)]",
                    isActive(seg.href)
                      ? "text-[var(--accent)]"
                      : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                  )}
                >
                  {seg.label}
                </Link>
              ))}
            </nav>

            {/* Settings gear icon */}
            <Link
              href="/settings"
              className={cn(
                "flex items-center justify-center w-8 h-8 rounded-[var(--radius-sm)] transition-colors duration-[var(--duration-short)]",
                isSettings
                  ? "text-[var(--accent)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--surface-raised)]"
              )}
              aria-label="Settings"
            >
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
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </Link>
          </div>
        </div>

        {/* 3-segment progress bar */}
        <div className="flex gap-[2px] h-[3px] -mt-[1px]">
          {segments.map((seg) => (
            <div
              key={seg.href}
              className={cn(
                "flex-1 rounded-full transition-colors duration-[var(--duration-short)]",
                isActive(seg.href)
                  ? "bg-[var(--nav-active)]"
                  : "bg-[var(--nav-inactive)]"
              )}
            />
          ))}
          {/* Deep Dive segment — lights up on /story/* */}
          <div
            className={cn(
              "flex-1 rounded-full transition-colors duration-[var(--duration-short)]",
              isDeepDive
                ? "bg-[var(--nav-active)]"
                : "bg-[var(--nav-inactive)]"
            )}
          />
        </div>
      </div>
    </header>
  );
}
