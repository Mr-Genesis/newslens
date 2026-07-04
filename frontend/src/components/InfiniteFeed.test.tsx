// WS-3 (#113): the InfiniteFeed component — render, cross-section dedupe, caught-up, retry, skeletons.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({ getFeed: vi.fn(), postImpressions: vi.fn().mockResolvedValue(undefined) }));

import { getFeed } from "@/lib/api";
import { InfiniteFeed } from "./InfiniteFeed";

const art = (id: number) => ({
  id, title: `S${id}`, url: `https://ex/${id}`, snippet: "snip", ai_summary: null,
  published_at: "2026-07-04T00:00:00Z", fetched_at: "2026-07-04T00:00:00Z",
  source: { id, name: "Src", url: "https://ex", is_paywalled: false }, topics: [], cluster_id: id,
});
const pageResp = (ids: number[], total = ids.length) => ({
  articles: ids.map(art), total, page: 1, per_page: 20, as_of: "T0",
});

beforeEach(() => vi.mocked(getFeed).mockReset());

describe("InfiniteFeed", () => {
  it("renders feed rows and the caught-up terminal when the window fits one page", async () => {
    vi.mocked(getFeed).mockResolvedValue(pageResp([1, 2]));
    render(<InfiniteFeed />);
    expect(await screen.findByText("S1")).toBeInTheDocument();
    expect(screen.getByText("S2")).toBeInTheDocument();
    expect(await screen.findByText(/all caught up/i)).toBeInTheDocument();
  });

  it("filters out cluster ids already shown above (cross-section dedupe)", async () => {
    vi.mocked(getFeed).mockResolvedValue(pageResp([1, 2, 3]));
    render(<InfiniteFeed excludeClusterIds={new Set([2])} />);
    expect(await screen.findByText("S1")).toBeInTheDocument();
    expect(screen.getByText("S3")).toBeInTheDocument();
    expect(screen.queryByText("S2")).not.toBeInTheDocument(); // deduped away
  });

  it("shows the ALL STORIES chapter break when asked", async () => {
    vi.mocked(getFeed).mockResolvedValue(pageResp([1]));
    render(<InfiniteFeed showHeader />);
    expect(await screen.findByText("S1")).toBeInTheDocument(); // let the feed settle first
    expect(screen.getByText("ALL STORIES")).toBeInTheDocument();
    expect(screen.getByText(/everything, newest first/i)).toBeInTheDocument();
  });

  it("shows a retry on initial failure and recovers on click", async () => {
    vi.mocked(getFeed)
      .mockRejectedValueOnce(new Error("API 500"))
      .mockResolvedValue(pageResp([1, 2]));
    render(<InfiniteFeed />);
    expect(await screen.findByText(/couldn't load more stories/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(await screen.findByText("S1")).toBeInTheDocument();
  });

  it("shows skeletons during the initial load", async () => {
    let resolve!: (v: unknown) => void;
    vi.mocked(getFeed).mockReturnValue(new Promise((r) => { resolve = r; }) as never);
    render(<InfiniteFeed />);
    expect(screen.getByLabelText("Loading stories")).toBeInTheDocument();
    resolve(pageResp([1]));
    await waitFor(() => expect(screen.getByText("S1")).toBeInTheDocument());
  });
});
