import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return { ...actual, getFeed: vi.fn() };
});

import { useInfiniteFeed } from "./useInfiniteFeed";
import { getFeed, type Article, type FeedResponse } from "@/lib/api";
import { store, peek, memoryBackend, _setBackend, _resetCache } from "@/lib/cache";

const FEED_KEY = "feed:all:all:20"; // default opts: perPage 20, no topic/sourceType

function article(id: number, title: string): Article {
  return {
    id,
    title,
    url: `https://x/${id}`,
    snippet: null,
    ai_summary: null,
    published_at: "2026-01-01T00:00:00Z",
    fetched_at: "2026-01-01T00:00:00Z",
    source: { id: 1, name: "S", url: "https://x", is_paywalled: false },
    topics: [],
    cluster_id: null,
  };
}
function resp(arts: Article[], total = 100): FeedResponse {
  return { articles: arts, total, page: 1, per_page: 20, as_of: "2026-01-01T00:00:00Z" };
}

beforeEach(() => {
  _setBackend(memoryBackend());
  _resetCache();
  vi.clearAllMocks();
});

describe("useInfiniteFeed cache seeding", () => {
  it("cold: loading → items once the first page loads, and writes page 1 through to cache", async () => {
    vi.mocked(getFeed).mockResolvedValue(resp([article(1, "A"), article(2, "B")]));
    const { result } = renderHook(() => useInfiniteFeed());

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.items.length).toBe(2));
    expect(result.current.items.map((a) => a.title)).toEqual(["A", "B"]);
    // cached for the next remount
    expect(peek<FeedResponse>(FEED_KEY)?.articles.map((a) => a.title)).toEqual(["A", "B"]);
  });

  it("seeds the first paint from cache (no skeleton), then replaces with the revalidated page 1", async () => {
    await store(FEED_KEY, resp([article(1, "CACHED")]));
    let resolveFresh: (r: FeedResponse) => void = () => {};
    vi.mocked(getFeed).mockReturnValue(
      new Promise<FeedResponse>((r) => {
        resolveFresh = r;
      })
    );

    const { result } = renderHook(() => useInfiniteFeed());
    // instant seed — status is idle (not loading), so InfiniteFeed shows rows not a skeleton
    expect(result.current.items.map((a) => a.title)).toEqual(["CACHED"]);
    expect(result.current.status).toBe("idle");

    resolveFresh(resp([article(2, "FRESH1"), article(3, "FRESH2")]));
    await waitFor(() =>
      expect(result.current.items.map((a) => a.title)).toEqual(["FRESH1", "FRESH2"])
    );
  });

  it("does not page before loadFirst pins the cursor even when seeded (WS-3 cursor safety, review #4)", async () => {
    await store(FEED_KEY, resp([article(1, "CACHED")]));
    // loadFirst hangs → the as_of cursor is never pinned and pageRef stays 0
    vi.mocked(getFeed).mockReturnValue(new Promise<FeedResponse>(() => {}));

    const { result } = renderHook(() => useInfiniteFeed());
    expect(result.current.status).toBe("idle"); // seeded from cache

    await act(async () => {
      await result.current.loadMore(); // a sentinel intersection would call this
    });

    // loadMore was a no-op (pageRef still 0): only loadFirst's single page-1 fetch fired — NOT a second
    // page-1 fetch with a null cursor (the WS-3 pinning violation the guard prevents).
    expect(vi.mocked(getFeed)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(getFeed).mock.calls[0][0]).toBe(1);
  });
});
