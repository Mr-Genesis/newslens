// WS-3 (#113): the infinite-feed hook — cursor threading, prefetch, dedupe, stale recovery, terminal.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ getFeed: vi.fn() }));

import { getFeed } from "@/lib/api";
import { useInfiniteFeed } from "./useInfiniteFeed";

const art = (id: number) => ({
  id, title: `S${id}`, url: `https://ex/${id}`, snippet: "s", ai_summary: null,
  published_at: "2026-07-04T00:00:00Z", fetched_at: "2026-07-04T00:00:00Z",
  source: { id, name: "Src", url: "https://ex", is_paywalled: false }, topics: [], cluster_id: id,
});
const pageResp = (ids: number[], opts: { total?: number; as_of?: string } = {}) => ({
  articles: ids.map(art), total: opts.total ?? 100, page: 1, per_page: 2, as_of: opts.as_of ?? "T0",
});
const ids = (r: { items: { id: number }[] }) => r.items.map((i) => i.id);

beforeEach(() => vi.mocked(getFeed).mockReset());
afterEach(() => vi.unstubAllGlobals());

describe("useInfiniteFeed", () => {
  it("loads page 1 on mount, pins the cursor, and prefetches page 2", async () => {
    vi.mocked(getFeed).mockImplementation(async (p) => pageResp(p === 1 ? [1, 2] : [3, 4]));
    const { result } = renderHook(() => useInfiniteFeed({ perPage: 2 }));

    await waitFor(() => expect(ids(result.current)).toEqual([1, 2]));
    expect(result.current.status).toBe("idle");
    // page 2 prefetched WITHOUT any loadMore, and carrying the pinned cursor
    await waitFor(() => expect(vi.mocked(getFeed).mock.calls.some((c) => c[0] === 2)).toBe(true));
    const p2call = vi.mocked(getFeed).mock.calls.find((c) => c[0] === 2)!;
    expect(p2call[4]).toBe("T0"); // as_of threaded
  });

  it("appends the next page, dedupes overlapping ids, and prefetches ahead", async () => {
    vi.mocked(getFeed).mockImplementation(async (p) => {
      if (p === 1) return pageResp([1, 2]);
      if (p === 2) return pageResp([2, 3]); // id 2 overlaps page 1
      return pageResp([4, 5]);
    });
    const { result } = renderHook(() => useInfiniteFeed({ perPage: 2 }));
    await waitFor(() => expect(ids(result.current)).toEqual([1, 2]));

    await act(async () => { await result.current.loadMore(); });

    expect(ids(result.current)).toEqual([1, 2, 3]); // 2 deduped away
    await waitFor(() => expect(vi.mocked(getFeed).mock.calls.some((c) => c[0] === 3)).toBe(true));
  });

  it("reaches the 'done' terminal when the window is exhausted", async () => {
    vi.mocked(getFeed).mockImplementation(async (p) =>
      p === 1 ? pageResp([1, 2], { total: 3 }) : pageResp([3], { total: 3 })
    );
    const { result } = renderHook(() => useInfiniteFeed({ perPage: 2 }));
    await waitFor(() => expect(ids(result.current)).toEqual([1, 2]));

    await act(async () => { await result.current.loadMore(); });

    expect(ids(result.current)).toEqual([1, 2, 3]);
    expect(result.current.status).toBe("done");
  });

  it("recovers from a stale cursor by restarting with the fresh one", async () => {
    vi.mocked(getFeed).mockImplementation(async (_p, _pp, _t, _st, asOf) => {
      if (!asOf) return pageResp([1, 2], { as_of: "T0" });                 // page 1, pins T0
      if (asOf === "T0") return { articles: [], total: 0, page: 2, per_page: 2, as_of: "T1" }; // STALE
      return pageResp([10, 11], { as_of: "T1" });                          // recovered under T1
    });
    const { result } = renderHook(() => useInfiniteFeed({ perPage: 2 }));
    await waitFor(() => expect(ids(result.current)).toEqual([1, 2]));

    await act(async () => { await result.current.loadMore(); });

    // stale detected → items reset → refetched under the fresh cursor
    await waitFor(() => expect(ids(result.current)).toEqual([10, 11]));
  });

  it("surfaces an error and retries the failed load", async () => {
    vi.mocked(getFeed)
      .mockRejectedValueOnce(new Error("API 500: err"))
      .mockImplementation(async () => pageResp([1, 2], { total: 2 }));
    const { result } = renderHook(() => useInfiniteFeed({ perPage: 2 }));
    await waitFor(() => expect(result.current.status).toBe("error"));

    await act(async () => { result.current.retry(); });

    await waitFor(() => expect(ids(result.current)).toEqual([1, 2]));
    expect(result.current.status).toBe("done"); // total 2 == one page → caught up
  });

  it("recovers when a mid-scroll page (a prefetch) fails and retry is tapped", async () => {
    // Regression (WS-3 review, HIGH): a rejected prefetch must not wedge retry by re-awaiting the
    // same dead promise. Page 1 succeeds + prefetches page 2; page 2 fails once, then recovers.
    let page2 = 0;
    vi.mocked(getFeed).mockImplementation(async (p) => {
      if (p === 1) return pageResp([1, 2], { total: 100 });
      if (p === 2) {
        page2 += 1;
        if (page2 === 1) throw new Error("API 500: prefetch blip");
        return pageResp([3, 4], { total: 100 });
      }
      return pageResp([5, 6], { total: 100 });
    });
    const { result } = renderHook(() => useInfiniteFeed({ perPage: 2 }));
    await waitFor(() => expect(ids(result.current)).toEqual([1, 2]));

    await act(async () => { await result.current.loadMore(); }); // consumes the rejected prefetch
    await waitFor(() => expect(result.current.status).toBe("error"));

    await act(async () => { result.current.retry(); }); // must issue a FRESH page-2 fetch
    await waitFor(() => expect(ids(result.current)).toEqual([1, 2, 3, 4]));
  });

  it("fires exactly one loadMore per sentinel intersection (single-fire guard)", async () => {
    let cb: (entries: { isIntersecting: boolean }[]) => void = () => {};
    const observe = vi.fn();
    vi.stubGlobal(
      "IntersectionObserver",
      vi.fn((c: typeof cb) => { cb = c; return { observe, disconnect: vi.fn(), unobserve: vi.fn() }; })
    );
    vi.mocked(getFeed).mockImplementation(async (p) => pageResp(p === 1 ? [1, 2] : [3, 4]));
    const { result } = renderHook(() => useInfiniteFeed({ perPage: 2 }));
    await waitFor(() => expect(ids(result.current)).toEqual([1, 2]));

    act(() => result.current.sentinelRef(document.createElement("div")));
    expect(observe).toHaveBeenCalled();

    // two intersections back-to-back must page in only ONCE
    await act(async () => { cb([{ isIntersecting: true }]); cb([{ isIntersecting: true }]); });
    await waitFor(() => expect(ids(result.current)).toEqual([1, 2, 3, 4]));
    expect(vi.mocked(getFeed).mock.calls.filter((c) => c[0] === 2).length).toBe(1);
  });
});
