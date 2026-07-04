// WS-8 (#118): the Settings System card — cold-start, success counts, unreachable, error surfacing.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ getPipeline: vi.fn() }));

import { getPipeline } from "@/lib/api";
import { SystemCard } from "./SystemCard";

const STATUS = (over = {}) => ({
  articles: { total: 100, by_embedding_status: { complete: 90, pending: 8, failed: 2 } },
  clusters: { total: 20, articles_clustered: 60 },
  freshness: { latest_article_fetched_at: new Date().toISOString(), latest_cluster_created_at: null },
  last_embedding_error: null,
  ...over,
});

beforeEach(() => vi.mocked(getPipeline).mockReset());

describe("SystemCard (WS-8)", () => {
  it("shows the cold-start waking state before data arrives", async () => {
    let resolve!: (v: unknown) => void;
    vi.mocked(getPipeline).mockReturnValue(new Promise((r) => { resolve = r; }) as never);
    render(<SystemCard />);
    expect(screen.getByText(/waking the pipeline/i)).toBeInTheDocument();
    resolve(STATUS()); // settle so teardown doesn't hang on the pending promise
    await screen.findByText("100");
  });

  it("renders pipeline counts on success", async () => {
    vi.mocked(getPipeline).mockResolvedValue(STATUS());
    render(<SystemCard />);
    expect(await screen.findByText("100")).toBeInTheDocument(); // articles total
    expect(screen.getByText("90")).toBeInTheDocument();          // embedded
    expect(screen.getByText("20")).toBeInTheDocument();          // clusters
  });

  it("shows the unreachable state on a cold fetch failure", async () => {
    vi.mocked(getPipeline).mockRejectedValueOnce(new Error("network")); // one call on mount
    render(<SystemCard />);
    expect(await screen.findByText(/unreachable/i)).toBeInTheDocument();
  });

  it("surfaces the last embedding error", async () => {
    vi.mocked(getPipeline).mockResolvedValue(STATUS({ last_embedding_error: "quota" }));
    render(<SystemCard />);
    expect(await screen.findByText(/quota/i)).toBeInTheDocument();
  });
});
