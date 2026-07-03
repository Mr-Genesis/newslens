import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";

import { SplashScreen } from "./SplashScreen";

describe("SplashScreen — branded app-open reveal", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("shows the wordmark and status label on first launch of a session", () => {
    render(<SplashScreen />);
    expect(screen.getByText("News")).toBeInTheDocument();
    expect(screen.getByText("Lens")).toBeInTheDocument();
    expect(screen.getByText(/assembling your briefing/i)).toBeInTheDocument();
  });

  it("does not show again once the session flag is set", () => {
    sessionStorage.setItem("newslens-splash-seen", "1");
    render(<SplashScreen />);
    expect(screen.queryByText("Lens")).toBeNull();
  });

  it("marks the splash seen after it auto-dismisses", () => {
    vi.useFakeTimers();
    try {
      render(<SplashScreen />);
      expect(sessionStorage.getItem("newslens-splash-seen")).toBeNull();
      act(() => {
        vi.advanceTimersByTime(3100); // hold is 2800ms (full mark choreography) + margin
      });
      expect(sessionStorage.getItem("newslens-splash-seen")).toBe("1");
    } finally {
      vi.useRealTimers();
    }
  });
});
