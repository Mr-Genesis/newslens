import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return { ...actual, getCluster: vi.fn() };
});

import { usePrefetchClusters, PREFETCH_TOP_N } from "./usePrefetchClusters";
import { getCluster, type ClusterDetail } from "@/lib/api";
import { store, peek, memoryBackend, _setBackend, _resetCache } from "@/lib/cache";

const detail = (id: number): ClusterDetail => ({
  id,
  title: `T${id}`,
  summary: "s",
  created_at: "2026-01-01T00:00:00Z",
  coherence: 0.8,
  sources: [],
});

beforeEach(() => {
  _setBackend(memoryBackend());
  _resetCache();
  vi.clearAllMocks();
  vi.mocked(getCluster).mockImplementation(async (id) => detail(id));
});

describe("usePrefetchClusters", () => {
  it("warms the top-N uncached cluster ids into the cache", async () => {
    renderHook(() => usePrefetchClusters([10, 11, 12, 13, 14]));

    await waitFor(() => expect(peek("cluster:10")).toBeDefined());
    expect(peek("cluster:12")).toBeDefined();
    // capped at PREFETCH_TOP_N → the rest are left cold
    expect(getCluster).toHaveBeenCalledTimes(PREFETCH_TOP_N);
    expect(peek("cluster:13")).toBeUndefined();
  });

  it("skips ids already in the cache (no redundant fetch)", async () => {
    await store("cluster:20", detail(20));
    renderHook(() => usePrefetchClusters([20, 21]));

    await waitFor(() => expect(peek("cluster:21")).toBeDefined());
    expect(getCluster).toHaveBeenCalledTimes(1); // only the uncached 21
    expect(getCluster).toHaveBeenCalledWith(21);
  });

  it("ignores nulls (unclustered fallback stories) without fetching", async () => {
    renderHook(() => usePrefetchClusters([null, undefined]));
    await Promise.resolve();
    expect(getCluster).not.toHaveBeenCalled();
  });
});
