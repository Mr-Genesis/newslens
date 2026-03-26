import { Suspense } from "react";
import StoryContent from "./StoryContent";

export default function StoryPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen"><p className="text-body text-[var(--text-muted)]">Loading...</p></div>}>
      <StoryContent />
    </Suspense>
  );
}
