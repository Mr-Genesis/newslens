import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { PullToRefresh } from "./PullToRefresh";

function pull(el: HTMLElement, dy: number) {
  fireEvent.touchStart(el, { touches: [{ clientY: 0 }] });
  fireEvent.touchMove(el, { touches: [{ clientY: dy }] });
  fireEvent.touchEnd(el);
}

describe("PullToRefresh (#99)", () => {
  it("refreshes when pulled past the threshold", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<PullToRefresh onRefresh={onRefresh}><div>content</div></PullToRefresh>);
    // 200px raw → resisted offset 80 ≥ 60 threshold → triggers
    pull(screen.getByText("content").parentElement as HTMLElement, 200);
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
  });

  it("does not refresh when released below the threshold", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<PullToRefresh onRefresh={onRefresh}><div>content</div></PullToRefresh>);
    // 100px raw → resisted offset 40 < 60 → snaps back, no refresh
    pull(screen.getByText("content").parentElement as HTMLElement, 100);
    await new Promise((r) => setTimeout(r, 20));
    expect(onRefresh).not.toHaveBeenCalled();
  });
});
