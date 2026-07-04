import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

// Stub the self-fetching children so this test is only about the briefing wiring.
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));
vi.mock("@/hooks/useImpressions", () => ({ useImpressions: () => ({ observe: () => {} }) }));
vi.mock("@/components/FollowRails", () => ({ FollowRails: () => null }));
vi.mock("@/components/InfiniteFeed", () => ({ InfiniteFeed: () => null }));
vi.mock("@/components/ui/DailyTriviaCard", () => ({ DailyTriviaCard: () => null }));
vi.mock("@/components/ui/PersonalizeBanner", () => ({ PersonalizeBanner: () => null }));
vi.mock("@/components/ui/WhileAwayCard", () => ({ WhileAwayCard: () => null }));
vi.mock("@/components/PullToRefresh", () => ({
  PullToRefresh: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return {
    ...actual,
    getBriefing: vi.fn(),
    getTopics: vi.fn().mockResolvedValue({ your_topics: [], explore_topics: [], trending_topics: [] }),
  };
});

import BriefingPage from "./page";
import { getBriefing, type Briefing, type BriefingStory } from "@/lib/api";
import { store, memoryBackend, _setBackend, _resetCache } from "@/lib/cache";

const story = (title: string): BriefingStory => ({
  title,
  summary: "S",
  cluster_id: 1,
  category: "World",
  source_count: 3,
  coherence: 0.8,
});
const briefing = (title: string): Briefing => ({
  stories: [story(title)],
  generated_at: new Date(0).toISOString(),
});

beforeEach(() => {
  _setBackend(memoryBackend());
  _resetCache();
  vi.clearAllMocks();
  localStorage.setItem("newslens-onboarded", "1"); // skip the first-run redirect
});

describe("BriefingPage cache-first paint", () => {
  it("paints the cached briefing immediately, then swaps in the revalidated one", async () => {
    await store("briefing", briefing("CACHED HERO"));
    let resolveFresh: (b: Briefing) => void = () => {};
    vi.mocked(getBriefing).mockReturnValue(
      new Promise<Briefing>((r) => {
        resolveFresh = r;
      })
    );

    render(<BriefingPage />);
    // Instant paint from cache — the network request is still pending.
    expect(screen.getByText("CACHED HERO")).toBeInTheDocument();

    resolveFresh(briefing("FRESH HERO"));
    await waitFor(() => expect(screen.getByText("FRESH HERO")).toBeInTheDocument());
  });

  it("shows the cold-start loader when nothing is cached", () => {
    vi.mocked(getBriefing).mockReturnValue(new Promise<Briefing>(() => {})); // never resolves
    render(<BriefingPage />);
    expect(screen.getByText(/assembling your briefing/i)).toBeInTheDocument();
  });
});
