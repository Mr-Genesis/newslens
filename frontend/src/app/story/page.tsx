import { Suspense } from "react";
import StoryContent from "./StoryContent";
import { StoryLoadingSkeleton } from "@/components/ui/Skeleton";

export default function StoryPage() {
  return (
    <Suspense fallback={<StoryLoadingSkeleton />}>
      <StoryContent />
    </Suspense>
  );
}
