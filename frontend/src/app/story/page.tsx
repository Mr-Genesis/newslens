import { Suspense } from "react";
import StoryContent from "./StoryContent";
import { LoadingScreen } from "@/components/ui/LoadingScreen";

export default function StoryPage() {
  return (
    <Suspense fallback={<LoadingScreen label="Loading story" />}>
      <StoryContent />
    </Suspense>
  );
}
