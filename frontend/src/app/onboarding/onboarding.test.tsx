import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/api", () => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
}));

import OnboardingPage from "./page";
import { getProfile, updateProfile } from "@/lib/api";

describe("Onboarding (E3) — interests-first, skippable", () => {
  beforeEach(() => {
    localStorage.clear();
    replace.mockClear();
    vi.mocked(getProfile).mockResolvedValue({
      profession: null,
      locale: "IN",
      interests: [],
    });
    vi.mocked(updateProfile).mockResolvedValue({
      profession: null,
      locale: "IN",
      interests: [],
    });
  });

  it("is interests-only (profession deferred off this screen) and skippable", async () => {
    render(<OnboardingPage />);
    expect(
      await screen.findByText(/what do you want to follow/i)
    ).toBeInTheDocument();
    // Profession is NOT collected here anymore (deferred to the Today banner).
    expect(
      screen.queryByPlaceholderText(/product engineer|doctor|trader/i)
    ).toBeNull();

    // Skippable without choosing anything.
    await userEvent.click(screen.getByRole("button", { name: /skip/i }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    // interests-only here; locale is auto-detected from the browser (Wave Q2), not hardcoded.
    expect(updateProfile).toHaveBeenCalledWith(
      expect.objectContaining({ interests: [] })
    );
    expect(localStorage.getItem("newslens-onboarded")).toBe("1");
  });

  it("shows the 'X of 3 set up' nudge that advances when an interest is picked", async () => {
    render(<OnboardingPage />);
    await screen.findByText(/what do you want to follow/i);
    expect(screen.getByText(/1 of 3 set up/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "AI" }));
    expect(screen.getByText(/2 of 3 set up/i)).toBeInTheDocument();
  });
});
