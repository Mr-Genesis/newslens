import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return <div className={cn("skeleton", className)} />;
}

/** Skeleton matching a briefing story card */
export function StoryCardSkeleton() {
  return (
    <div className="py-[var(--space-lg)] space-y-3">
      <Skeleton className="h-5 w-3/4" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <div className="flex gap-3 mt-2">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-10" />
      </div>
    </div>
  );
}

/** Skeleton matching the deep-dive page — eyebrow, title, lead, meta chips,
 *  AI summary box and source rows, so it dovetails into the real content. */
export function DeepDiveSkeleton() {
  return (
    <div className="space-y-6">
      {/* Eyebrow + title */}
      <div className="space-y-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-7 w-11/12" />
        <Skeleton className="h-7 w-3/5" />
      </div>
      {/* Lead + meta chips */}
      <div className="space-y-3">
        <Skeleton className="h-4 w-full" />
        <div className="flex gap-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-20" />
        </div>
      </div>
      {/* AI summary box */}
      <div className="rounded-[var(--radius-md)] bg-[var(--drill-muted)] p-4 space-y-2">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-3/4" />
      </div>
      {/* Source rows */}
      {[1, 2, 3].map((i) => (
        <div key={i} className="space-y-2 py-4">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-12" />
          </div>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-3 w-28" />
        </div>
      ))}
    </div>
  );
}

/** Full-page deep-dive route skeleton — DeepDiveSkeleton inside the story
 *  container. Used as the route/Suspense fallback on story open so the
 *  transition shows the content shape instead of a generic spinner. */
export function StoryLoadingSkeleton() {
  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-md)] pb-[var(--space-2xl)] pt-[var(--space-md)]">
      <DeepDiveSkeleton />
    </div>
  );
}

/** Skeleton matching a discover card */
export function DiscoverCardSkeleton() {
  return (
    <div className="rounded-[var(--radius-md)] bg-[var(--surface-raised)] p-4 space-y-3 h-[320px]">
      <div className="flex justify-end">
        <Skeleton className="h-5 w-16" />
      </div>
      <Skeleton className="h-6 w-full" />
      <Skeleton className="h-6 w-3/4" />
      <div className="space-y-2 mt-4">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
      <div className="flex gap-2 mt-auto pt-4">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  );
}
