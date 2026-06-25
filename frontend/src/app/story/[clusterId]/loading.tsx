import { StoryLoadingSkeleton } from "@/components/ui/Skeleton";

/** Route-level loading for the deep-dive — a content-shaped skeleton that
 *  mirrors the story layout instead of the generic app loader. */
export default function Loading() {
  return <StoryLoadingSkeleton />;
}
