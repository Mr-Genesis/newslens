import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({
  getFollows: vi.fn(),
  addFollow: vi.fn(),
  removeFollow: vi.fn(),
}));

import { FollowButton } from "./FollowButton";
import { getFollows, addFollow, removeFollow } from "@/lib/api";

describe("FollowButton", () => {
  beforeEach(() => {
    vi.mocked(getFollows).mockResolvedValue([]);
    vi.mocked(addFollow).mockResolvedValue({
      id: 1,
      kind: "topic",
      value: "AI",
      created_at: "2026-06-24T00:00:00Z",
    });
    vi.mocked(removeFollow).mockResolvedValue(undefined);
  });

  it("follows, then unfollows, reflecting state each way", async () => {
    render(<FollowButton kind="topic" value="AI" />);

    // Starts unfollowed (getFollows → []).
    const btn = await screen.findByRole("button", { name: /^follow$/i });
    expect(btn).toHaveAttribute("aria-pressed", "false");

    // Follow → POST with (kind, value), reflects "Following".
    await userEvent.click(btn);
    expect(addFollow).toHaveBeenCalledWith("topic", "AI");
    await screen.findByRole("button", { name: /following/i });
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");

    // Unfollow → DELETE by the id returned from addFollow, back to "Follow".
    await userEvent.click(screen.getByRole("button"));
    expect(removeFollow).toHaveBeenCalledWith(1);
    await screen.findByRole("button", { name: /^follow$/i });
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "false");
  });

  it("reflects an already-followed item on mount and unfollows by its id", async () => {
    vi.mocked(getFollows).mockResolvedValue([
      { id: 5, kind: "topic", value: "AI", created_at: "2026-06-24T00:00:00Z" },
    ]);
    render(<FollowButton kind="topic" value="AI" />);

    const btn = await screen.findByRole("button", { name: /following/i });
    expect(btn).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(btn);
    expect(removeFollow).toHaveBeenCalledWith(5);
    await screen.findByRole("button", { name: /^follow$/i });
  });

  it("matches an existing follow case- and whitespace-insensitively", async () => {
    vi.mocked(getFollows).mockResolvedValue([
      { id: 9, kind: "saved_search", value: "opec cuts", created_at: "x" },
    ]);
    render(<FollowButton kind="saved_search" value="  OPEC Cuts " label="Follow this search" />);
    // Already-followed → shows the followed state despite case/whitespace differences.
    await screen.findByRole("button", { name: /following/i });
  });

  it("uses a custom label for the unfollowed state", async () => {
    render(<FollowButton kind="saved_search" value="opec" label="Follow this search" />);
    await screen.findByRole("button", { name: /follow this search/i });
  });

  it("rolls back to unfollowed if the follow request fails", async () => {
    vi.mocked(addFollow).mockRejectedValueOnce(new Error("network"));
    render(<FollowButton kind="topic" value="AI" />);
    const btn = await screen.findByRole("button", { name: /^follow$/i });

    await userEvent.click(btn);
    // After the failed request it returns to the unfollowed state.
    await screen.findByRole("button", { name: /^follow$/i });
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "false");
  });
});
