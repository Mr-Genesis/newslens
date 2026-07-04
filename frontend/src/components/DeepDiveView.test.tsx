import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

// Isolate the wiring: stub the self-fetching lens children + the deep-dive's own impact fetch.
vi.mock("next/navigation", () => ({ useParams: () => ({}) }));
vi.mock("@/components/ui/AISummaryBox", () => ({ AISummaryBox: () => null }));
vi.mock("@/components/ui/ImpactCard", () => ({ ImpactCard: () => null }));
vi.mock("@/components/ui/AskBox", () => ({ AskBox: () => null }));
vi.mock("@/components/ui/FrameworksCard", () => ({ FrameworksCard: () => null }));
vi.mock("@/components/ui/EntityChips", () => ({ EntityChips: () => null }));
vi.mock("@/components/ui/ConsensusRow", () => ({ ConsensusRow: () => null }));
vi.mock("@/components/ui/TriviaCard", () => ({ TriviaCard: () => null }));
vi.mock("@/components/ui/AgreementMeter", () => ({ AgreementMeter: () => null }));
vi.mock("@/components/SourceCard", () => ({ SourceCard: () => null }));
vi.mock("@/components/SourceSpectrum", () => ({ SourceSpectrum: () => null }));
vi.mock("@/components/ui/Collapsible", () => ({
  Collapsible: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return {
    ...actual,
    getCluster: vi.fn(),
    getClusterImpact: vi.fn().mockResolvedValue({ unavailable: true }),
    postDwell: vi.fn().mockResolvedValue(undefined),
    postFeedback: vi.fn().mockResolvedValue(undefined),
  };
});

import DeepDiveView from "./DeepDiveView";
import { getCluster, type ClusterDetail } from "@/lib/api";
import { store, memoryBackend, _setBackend, _resetCache } from "@/lib/cache";

const cluster = (title: string): ClusterDetail => ({
  id: 5,
  title,
  summary: "A summary sentence.",
  created_at: new Date(0).toISOString(),
  coherence: 0.8,
  sources: [],
});

beforeEach(() => {
  _setBackend(memoryBackend());
  _resetCache();
  vi.clearAllMocks();
});

describe("DeepDiveView cache-first paint", () => {
  it("paints a cached cluster instantly (no skeleton), then revalidates", async () => {
    await store("cluster:5", cluster("CACHED STORY TITLE"));
    let resolveFresh: (c: ClusterDetail) => void = () => {};
    vi.mocked(getCluster).mockReturnValue(
      new Promise<ClusterDetail>((r) => {
        resolveFresh = r;
      })
    );

    render(<DeepDiveView clusterIdOverride={5} />);
    // instant paint from cache — the /clusters/5 request is still pending
    expect(screen.getByText("CACHED STORY TITLE")).toBeInTheDocument();

    resolveFresh(cluster("FRESH STORY TITLE"));
    await waitFor(() => expect(screen.getByText("FRESH STORY TITLE")).toBeInTheDocument());
  });

  it("shows the error card when the fetch fails with nothing cached", async () => {
    vi.mocked(getCluster).mockRejectedValue(new Error("boom"));
    render(<DeepDiveView clusterIdOverride={9} />);
    await waitFor(() =>
      expect(screen.getByText(/couldn.t load this story/i)).toBeInTheDocument()
    );
  });
});
