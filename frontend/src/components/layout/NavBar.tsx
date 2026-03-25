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

  // Deep Dive pages don't highlight any tab
  const isDeepDive = pathname.startsWith("/story/");

  function isActive(href: string) {
    if (isDeepDive) return false;
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

          {/* Nav tabs */}
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
