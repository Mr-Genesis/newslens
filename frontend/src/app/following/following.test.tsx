import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", () => ({
  getFollows: vi.fn(),
  removeFollow: vi.fn(),
}));

import FollowingPage from "./page";
import { getFollows, removeFollow } from "@/lib/api";

describe("Following management view", () => {
  beforeEach(() => {
    vi.mocked(removeFollow).mockResolvedValue(undefined);
    vi.mocked(getFollows).mockResolvedValue([
      { id: 1, kind: "topic", value: "AI" },
      { id: 2, kind: "saved_search", value: "opec cuts" },
      { id: 3, kind: "entity", value: "Tesla" },
    ]);
  });

  it("lists every follow, regardless of kind", async () => {
    render(<FollowingPage />);
    expect(await screen.findByText("AI")).toBeInTheDocument();
    expect(screen.getByText("opec cuts")).toBeInTheDocument();
    expect(screen.getByText("Tesla")).toBeInTheDocument();
  });

  it("unfollows an item with one tap and drops it from the list", async () => {
    render(<FollowingPage />);
    await screen.findByText("AI");

    await userEvent.click(screen.getByRole("button", { name: /unfollow AI/i }));
    expect(removeFollow).toHaveBeenCalledWith(1);

    await waitFor(() => expect(screen.queryByText("AI")).toBeNull());
    // The others are untouched.
    expect(screen.getByText("opec cuts")).toBeInTheDocument();
    expect(screen.getByText("Tesla")).toBeInTheDocument();
  });

  it("shows an empty state when nothing is followed", async () => {
    vi.mocked(getFollows).mockResolvedValue([]);
    render(<FollowingPage />);
    expect(
      await screen.findByText(/not following anything yet/i)
    ).toBeInTheDocument();
  });
});
