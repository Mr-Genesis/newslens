import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StoryCard } from "./StoryCard";
import type { BriefingStory } from "@/lib/api";

const base: BriefingStory = {
  title: "A story", summary: "Summary text.", cluster_id: 1, category: "world",
  source_count: 2, coherence: 0.9, is_read: true,
};

describe("StoryCard tier badge (Phase 2 · #78)", () => {
  it("shows a RESEARCH badge for a research-tier story", () => {
    render(<StoryCard story={{ ...base, title: "Cardiology trial", tier: "research" }} />);
    expect(screen.getByText("RESEARCH")).toBeInTheDocument();
  });

  it("shows no tier badge for an ordinary news story", () => {
    render(<StoryCard story={{ ...base, tier: null }} />);
    expect(screen.queryByText("RESEARCH")).toBeNull();
    expect(screen.queryByText("EXPERT")).toBeNull();
  });
});
