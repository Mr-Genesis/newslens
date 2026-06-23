import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
}));

import { PersonalizeBanner, IMPACT_SEEN_KEY } from "./PersonalizeBanner";
import { getProfile } from "@/lib/api";

describe("PersonalizeBanner (E3) — appears after first impact", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(getProfile).mockResolvedValue({
      profession: null,
      locale: "IN",
      interests: ["AI"],
    });
  });

  it("does NOT render until the user has met an impact card", async () => {
    const { container } = render(<PersonalizeBanner />);
    // No IMPACT_SEEN_KEY → never shows.
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(screen.queryByText(/personalize your impact lens/i)).toBeNull();
  });

  it("appears after the first impact when profession is unset", async () => {
    localStorage.setItem(IMPACT_SEEN_KEY, "1");
    render(<PersonalizeBanner />);
    expect(
      await screen.findByText(/personalize your impact lens/i)
    ).toBeInTheDocument();
    // "X of 3 set up" nudge present (interests set + locale default = 2 of 3).
    expect(screen.getByText(/2 of 3 set up/i)).toBeInTheDocument();
  });

  it("stays hidden once a profession is already set", async () => {
    localStorage.setItem(IMPACT_SEEN_KEY, "1");
    vi.mocked(getProfile).mockResolvedValue({
      profession: "Investor",
      locale: "IN",
      interests: [],
    });
    const { container } = render(<PersonalizeBanner />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("stays hidden once dismissed", async () => {
    localStorage.setItem(IMPACT_SEEN_KEY, "1");
    localStorage.setItem("newslens-personalize-dismissed", "1");
    const { container } = render(<PersonalizeBanner />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
