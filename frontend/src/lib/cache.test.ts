import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  peek,
  load,
  store,
  revalidate,
  memoryBackend,
  _setBackend,
  _resetCache,
  CACHE_TTL_MS,
  CACHE_LIMITS,
  type PersistBackend,
} from "./cache";

beforeEach(() => {
  _setBackend(memoryBackend());
  _resetCache();
});

describe("cache core (two-tier SWR)", () => {
  it("store() then peek() returns the data synchronously (memory tier)", async () => {
    await store("briefing", { a: 1 });
    expect(peek("briefing")).toEqual({ a: 1 });
  });

  it("peek() returns undefined for a missing key", () => {
    expect(peek("nope")).toBeUndefined();
  });

  it("load() falls back to the persistent backend and hydrates memory", async () => {
    // Seed the backend directly, bypassing the in-memory Map, to simulate a fresh app launch
    // where nothing is in memory yet but the last session persisted to IndexedDB.
    const backend = memoryBackend();
    await backend.set("cluster:7", { data: { title: "Persisted" }, storedAt: Date.now() });
    _setBackend(backend);

    expect(peek("cluster:7")).toBeUndefined(); // not in memory yet
    expect(await load("cluster:7")).toEqual({ title: "Persisted" });
    expect(peek("cluster:7")).toEqual({ title: "Persisted" }); // hydrated into memory
  });

  it("peek()/load() honor maxAgeMs (a stale entry is a miss)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    await store("feed:p1", ["x"]);
    vi.setSystemTime(1000);
    expect(peek("feed:p1", 500)).toBeUndefined(); // age 1000 > 500 → miss
    expect(peek("feed:p1", 2000)).toEqual(["x"]); // within window → hit
    expect(await load("feed:p1", 500)).toBeUndefined();
    vi.useRealTimers();
  });

  it("revalidate() runs the fetcher, write-throughs the result, and returns it", async () => {
    const fresh = await revalidate("briefing", async () => ({ stories: [1, 2] }));
    expect(fresh).toEqual({ stories: [1, 2] });
    expect(peek("briefing")).toEqual({ stories: [1, 2] }); // written through both tiers
  });

  it("revalidate() dedupes concurrent calls for the same key (fetcher fires once)", async () => {
    let calls = 0;
    let resolveFetch: (v: unknown) => void = () => {};
    const fetcher = () => {
      calls++;
      return new Promise((r) => {
        resolveFetch = r;
      });
    };

    const p1 = revalidate("k", fetcher);
    const p2 = revalidate("k", fetcher);
    expect(calls).toBe(1); // single in-flight request shared

    resolveFetch("VALUE");
    expect(await p1).toBe("VALUE");
    expect(await p2).toBe("VALUE");

    // in-flight cleared on settle → a later revalidate issues a fresh fetch (the deferred fetcher is
    // NOT re-used, so its call count stays 1; the new immediate fetcher supplies the value).
    const again = await revalidate("k", async () => "AGAIN");
    expect(again).toBe("AGAIN");
    expect(calls).toBe(1);
  });

  it("a rejected revalidate() clears the in-flight slot so a retry can re-fetch", async () => {
    let calls = 0;
    const boom = () => {
      calls++;
      return Promise.reject(new Error("network"));
    };
    await expect(revalidate("k", boom)).rejects.toThrow("network");
    await expect(revalidate("k", boom)).rejects.toThrow("network");
    expect(calls).toBe(2); // not wedged on the first rejected promise
  });
});

describe("cache eviction (TTL + oldest-first)", () => {
  it("prunes entries past their namespace TTL on the next write", async () => {
    const backend = memoryBackend();
    _setBackend(backend);
    vi.useFakeTimers();
    vi.setSystemTime(0);
    await store("feed:old", [1]); // feed TTL is 30m
    vi.setSystemTime(CACHE_TTL_MS.feed + 1000); // now well past it
    await store("briefing", { stories: [] }); // any write triggers the prune

    const keys = (await backend.entries()).map(([k]) => k);
    expect(keys).not.toContain("feed:old"); // expired → dropped from the backend
    expect(keys).toContain("briefing");
    expect(peek("feed:old")).toBeUndefined(); // and from memory
    vi.useRealTimers();
  });

  it("evicts the oldest-written entries once over the count cap", async () => {
    const backend = memoryBackend();
    _setBackend(backend);
    vi.useFakeTimers();
    const n = CACHE_LIMITS.maxEntries + 3;
    for (let i = 0; i < n; i++) {
      vi.setSystemTime(i * 1000); // strictly increasing storedAt; all within cluster's 2h TTL
      await store(`cluster:${i}`, { i });
    }
    const keys = (await backend.entries()).map(([k]) => k);
    expect(keys.length).toBe(CACHE_LIMITS.maxEntries); // capped
    expect(keys).not.toContain("cluster:0"); // three oldest evicted
    expect(keys).not.toContain("cluster:1");
    expect(keys).not.toContain("cluster:2");
    expect(keys).toContain(`cluster:${n - 1}`); // newest kept
    vi.useRealTimers();
  });

  it("evicts oldest to stay under the byte ceiling", async () => {
    const backend = memoryBackend();
    _setBackend(backend);
    const orig = { ...CACHE_LIMITS };
    CACHE_LIMITS.maxBytes = 100; // isolate the size path from the count path
    CACHE_LIMITS.maxEntries = 1000;
    try {
      vi.useFakeTimers();
      const big = "x".repeat(80); // ~82 bytes stringified — two exceed the 100B ceiling
      vi.setSystemTime(1);
      await store("cluster:a", big);
      vi.setSystemTime(2);
      await store("cluster:b", big);
      const keys = (await backend.entries()).map(([k]) => k);
      expect(keys).toContain("cluster:b"); // newest kept
      expect(keys).not.toContain("cluster:a"); // oldest evicted to fit
      vi.useRealTimers();
    } finally {
      CACHE_LIMITS.maxBytes = orig.maxBytes;
      CACHE_LIMITS.maxEntries = orig.maxEntries;
    }
  });

  it("keeps a lone entry that exceeds the byte ceiling — no self-eviction on its own write (review #2)", async () => {
    const backend = memoryBackend();
    _setBackend(backend);
    const orig = { ...CACHE_LIMITS };
    CACHE_LIMITS.maxBytes = 50;
    try {
      const huge = "x".repeat(200); // ~202 bytes stringified, well over the 50B ceiling
      await store("cluster:1", huge);
      expect(peek("cluster:1")).toBe(huge); // retained, not wiped by the write that stored it
      expect((await backend.entries()).some(([k]) => k === "cluster:1")).toBe(true);
    } finally {
      Object.assign(CACHE_LIMITS, orig);
    }
  });

  it("bounds the memory tier even when the persistent backend rejects every write (review #3)", async () => {
    const failing: PersistBackend = {
      get: async () => undefined,
      set: async () => {
        throw new Error("QuotaExceeded");
      },
      del: async () => {},
      entries: async () => [],
    };
    _setBackend(failing);
    const orig = { ...CACHE_LIMITS };
    CACHE_LIMITS.maxEntries = 3;
    try {
      vi.useFakeTimers();
      for (let i = 0; i < 6; i++) {
        vi.setSystemTime(i + 1); // strictly increasing storedAt
        await store(`cluster:${i}`, { i }); // backend.set throws → enforceLimits is skipped
      }
      // memory is still capped to the 3 newest (trimMemory runs regardless of the backend)
      expect(peek("cluster:0")).toBeUndefined();
      expect(peek("cluster:1")).toBeUndefined();
      expect(peek("cluster:2")).toBeUndefined();
      expect(peek("cluster:3")).toBeDefined();
      expect(peek("cluster:5")).toBeDefined();
      vi.useRealTimers();
    } finally {
      Object.assign(CACHE_LIMITS, orig);
    }
  });
});
