"use client";

import { useSearchParams } from "next/navigation";
import DeepDiveView from "@/components/DeepDiveView";
import { ArticleView } from "@/components/ArticleView";

export default function StoryContent() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id");
  const aid = searchParams.get("aid"); // unclustered fallback article (/story?aid=N)

  if (id) return <DeepDiveView clusterIdOverride={Number(id)} />;
  if (aid) return <ArticleView articleId={Number(aid)} />;

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-body text-[var(--text-muted)]">No story selected</p>
    </div>
  );
}
