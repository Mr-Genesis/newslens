import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

import { useCachedResource } from "./useCachedResource";
import { store, memoryBackend, _setBackend, _resetCache } from "@/lib/cache";

beforeEach(() => {
  _setBackend(memoryBackend());
  _resetCache();
});

const NO_FOCUS = { revalidateOnFocus: false } as const;

describe("useCachedResource", () => {
  it("cold cache: loading → fresh once the fetcher resolves", async () => {
    const fetcher = vi.fn().mockResolvedValue({ v: 1 });
    const { result } = renderHook(() => useCachedResource("briefing", fetcher, NO_FOCUS));

    expect(result.current.status).toBe("loading");
    expect(result.current.data).toBeNull();

    await waitFor(() => expect(result.current.status).toBe("fresh"));
    expect(result.current.data).toEqual({ v: 1 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("warm memory: paints cached data immediately (stale), then swaps in fresh", async () => {
    await store("briefing", { v: "cached" });
    const fetcher = vi.fn().mockResolvedValue({ v: "fresh" });
    const { result } = renderHook(() => useCachedResource("briefing", fetcher, NO_FOCUS));

    expect(result.current.data).toEqual({ v: "cached" }); // instant paint, no await
    expect(result.current.status).toBe("stale");

    await waitFor(() => expect(result.current.status).toBe("fresh"));
    expect(result.current.data).toEqual({ v: "fresh" });
  });

  it("keeps cached data on a failed revalidate (never blanks to error)", async () => {
    await store("cluster:1", { v: "cached" });
    const fetcher = vi.fn(() => Promise.reject(new Error("net")));
    const { result } = renderHook(() => useCachedResource("cluster:1", fetcher, NO_FOCUS));

    expect(result.current.data).toEqual({ v: "cached" });
    await waitFor(() => expect(result.current.validating).toBe(false));
    expect(result.current.data).toEqual({ v: "cached" }); // survived the failure
    expect(result.current.status).toBe("stale");
  });

  it("surfaces error when the fetcher fails and nothing is cached", async () => {
    const fetcher = vi.fn(() => Promise.reject(new Error("net")));
    const { result } = renderHook(() => useCachedResource("cluster:9", fetcher, NO_FOCUS));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.data).toBeNull();
  });

  it("is disabled when key is null (no fetch)", async () => {
    const fetcher = vi.fn().mockResolvedValue({});
    const { result } = renderHook(() => useCachedResource(null, fetcher, NO_FOCUS));

    expect(result.current.data).toBeNull();
    expect(result.current.status).toBe("loading");
    await Promise.resolve();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("drops a superseded (old-key) revalidation — A→B keeps B even if A resolves late (review #1)", async () => {
    // Regression (adversarial review, HIGH): navigating between two cached resources changes the hook
    // key IN PLACE (no remount, as DeepDiveView does). A slow in-flight run for the old key must NOT
    // write its data into the new key's snapshot (cross-story torn read).
    let resolveA: (v: { v: string }) => void = () => {};
    const fetcherA = () => new Promise<{ v: string }>((r) => (resolveA = r));
    const fetcherB = () => Promise.resolve({ v: "B" });

    const { result, rerender } = renderHook(
      ({ k, f }: { k: string; f: () => Promise<{ v: string }> }) => useCachedResource(k, f, NO_FOCUS),
      { initialProps: { k: "story:a", f: fetcherA } }
    );
    expect(result.current.status).toBe("loading"); // A is in flight, nothing cached

    rerender({ k: "story:b", f: fetcherB });
    await waitFor(() => expect(result.current.data).toEqual({ v: "B" }));

    resolveA({ v: "A" }); // the stale story-A request finally lands
    await Promise.resolve();
    await Promise.resolve();
    expect(result.current.data).toEqual({ v: "B" }); // B survived — A's late result was dropped
    expect(result.current.status).toBe("fresh");
  });
});
