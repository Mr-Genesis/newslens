"use client";

import { useSearchParams } from "next/navigation";
import DeepDiveView from "@/components/DeepDiveView";

export default function StoryContent() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id");

  if (!id) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-body text-[var(--text-muted)]">No story selected</p>
      </div>
    );
  }

  return <DeepDiveView clusterIdOverride={Number(id)} />;
}
