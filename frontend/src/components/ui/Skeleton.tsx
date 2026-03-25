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
    <div className="py-[var(--space-xl)] space-y-3">
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

/** Skeleton matching the deep-dive page */
export function DeepDiveSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-7 w-4/5" />
      {/* AI summary box */}
      <div className="rounded-[var(--radius-md)] bg-[var(--drill-muted)] p-4 space-y-2">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-3/4" />
      </div>
      {/* Source cards */}
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

/** Skeleton matching a discover card */
export function DiscoverCardSkeleton() {
  return (
    <div className="rounded-[var(--radius-md)] bg-[var(--surface-raised)] p-6 space-y-4 h-[360px]">
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
