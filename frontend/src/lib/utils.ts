import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a date as relative time: "2h ago", "3d ago", etc. */
export function relativeTime(date: string | Date): string {
  const now = Date.now();
  const then = new Date(date).getTime();
  const diff = now - then;

  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  return "just now";
}

/** Return the correct story URL for web (dynamic route) vs Capacitor (query param) */
export function storyHref(clusterId: number): string {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return `/story?id=${clusterId}`;
  }
  return `/story/${clusterId}`;
}

/** Check if a briefing timestamp is stale (>4 hours old) */
export function isStale(date: string | Date): boolean {
  const fourHours = 4 * 60 * 60 * 1000;
  return Date.now() - new Date(date).getTime() > fourHours;
}
