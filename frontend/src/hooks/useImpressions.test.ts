// WS-1 (#111): the shared impression hook — buffer, session-dedupe, cap, flush, re-buffer-once.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ postImpressions: vi.fn() }));

import { useImpressions } from "./useImpressions";
import { postImpressions } from "@/lib/api";

describe("useImpressions", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(postImpressions).mockReset().mockResolvedValue(undefined);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("buffers via logNow, dedupes within the session, and flushes on the interval", async () => {
    const { result } = renderHook(() => useImpressions("discover"));
    act(() => {
      result.current.logNow({ articleId: 7 });
      result.current.logNow({ articleId: 7 }); // session dup — dropped client-side
      result.current.logNow({ clusterId: 3 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000); // interval flush
    });
    expect(postImpressions).toHaveBeenCalledTimes(1);
    const items = vi.mocked(postImpressions).mock.calls[0][0];
    expect(items).toHaveLength(2);
    expect(items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ article_id: 7, surface: "discover" }),
        expect.objectContaining({ cluster_id: 3, surface: "discover" }),
      ])
    );
  });

  it("caps the buffer at 200 (drop-oldest)", async () => {
    const { result } = renderHook(() => useImpressions("feed"));
    act(() => {
      for (let i = 1; i <= 250; i++) result.current.logNow({ articleId: i });
    });
    await act(async () => {
      await result.current.flush();
    });
    const items = vi.mocked(postImpressions).mock.calls[0][0];
    expect(items).toHaveLength(200);
    expect(items[0]).toEqual(expect.objectContaining({ article_id: 51 })); // oldest 50 dropped
  });

  it("re-buffers ONCE when the flush fails (cold backend), then drops on repeat failure", async () => {
    vi.mocked(postImpressions).mockRejectedValue(new Error("503"));
    const { result } = renderHook(() => useImpressions("briefing"));
    act(() => {
      result.current.logNow({ clusterId: 11 });
    });
    await act(async () => {
      await result.current.flush(); // fails → re-buffered
    });
    await act(async () => {
      await result.current.flush(); // fails again → dropped
    });
    await act(async () => {
      await result.current.flush(); // nothing left → no call
    });
    expect(postImpressions).toHaveBeenCalledTimes(2);
  });

  it("ignores empty targets", async () => {
    const { result } = renderHook(() => useImpressions("rail"));
    act(() => {
      result.current.logNow({});
    });
    await act(async () => {
      await result.current.flush();
    });
    expect(postImpressions).not.toHaveBeenCalled();
  });
});
