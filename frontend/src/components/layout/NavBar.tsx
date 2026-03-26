"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

export function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const isDeepDive = pathname.startsWith("/story");

  return (
    <header
      className={cn(
        "fixed top-0 left-0 right-0 z-50",
        "bg-[var(--bg)] border-b border-[var(--border)]",
        "pt-[var(--safe-top)]"
      )}
      style={{ WebkitBackfaceVisibility: "hidden" }}
    >
      <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)]">
        <div className="flex items-center justify-between h-[var(--top-bar-height)]">
          {isDeepDive ? (
            /* Deep Dive: back arrow + truncated title */
            <button
              onClick={() => router.back()}
              className="flex items-center gap-2 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors min-h-[44px]"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M19 12H5" />
                <path d="M12 19l-7-7 7-7" />
              </svg>
              <span className="text-small font-medium">Back</span>
            </button>
          ) : (
            /* Default: Logo */
            <Link href="/" className="flex items-baseline shrink-0">
              <span className="text-[20px] font-semibold text-[var(--text-primary)] font-[family-name:var(--font-fraunces)]">
                News
              </span>
              <span className="text-[20px] font-semibold text-[var(--accent)] font-[family-name:var(--font-fraunces)]">
                Lens
              </span>
            </Link>
          )}

          {/* Right action — contextual */}
          {!isDeepDive && (
            <div className="flex items-center gap-1">
              {/* Search icon placeholder */}
              <button
                className="flex items-center justify-center w-10 h-10 rounded-full text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--surface-raised)] transition-colors"
                aria-label="Search"
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="M21 21l-4.35-4.35" />
                </svg>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
