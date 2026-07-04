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
});
