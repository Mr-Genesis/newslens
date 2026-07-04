// WS-2 (#112): the News-You-Follow rails — pager, badges, badge-clear-on-tap.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api", () => ({
  getFollowRails: vi.fn(),
  markFollowSeen: vi.fn().mockResolvedValue(undefined),
}));

import { FollowRails } from "./FollowRails";
import { getFollowRails, markFollowSeen } from "@/lib/api";

const rail = (over = {}) => ({
  follow_id: 1, kind: "saved_search", value: "US Iran war", total: 4, new_count: 3,
  stories: [
    { cluster_id: 10, title: "Strikes reported", summary: "s", source_count: 3 },
    { cluster_id: 11, title: "Talks resume", summary: "s", source_count: 2 },
  ],
  ...over,
});

describe("FollowRails", () => {
  beforeEach(() => {
    push.mockReset();
    vi.mocked(markFollowSeen).mockClear().mockResolvedValue(undefined);
  });

  it("renders nothing when the user follows nothing (briefing must not break)", async () => {
    vi.mocked(getFollowRails).mockResolvedValue([]);
    const { container } = render(<FollowRails />);
    await waitFor(() => expect(getFollowRails).toHaveBeenCalled());
    expect(container.querySelector('[aria-label="News you follow"]')).toBeNull();
  });

  it("renders a panel with the follow name, the N-new badge, and its headlines", async () => {
    vi.mocked(getFollowRails).mockResolvedValue([rail()]);
    render(<FollowRails />);
    expect(await screen.findByText("US Iran war")).toBeInTheDocument();
    expect(screen.getByLabelText("3 new stories")).toBeInTheDocument();
    expect(screen.getByText("Strikes reported")).toBeInTheDocument();
  });

  it("caps the badge at 9+", async () => {
    vi.mocked(getFollowRails).mockResolvedValue([rail({ new_count: 42 })]);
    render(<FollowRails />);
    expect(await screen.findByLabelText("42 new stories")).toHaveTextContent("9+");
  });

  it("tapping a story clears THAT rail's badge and opens the story with the rail surface", async () => {
    vi.mocked(getFollowRails).mockResolvedValue([rail()]);
    render(<FollowRails />);
    await userEvent.click(await screen.findByText("Strikes reported"));
    expect(markFollowSeen).toHaveBeenCalledWith(1);
    expect(push).toHaveBeenCalledWith("/story/10");
    await waitFor(() => expect(screen.queryByLabelText(/new stories/)).toBeNull()); // badge cleared
  });

  it("shows the watching empty state for a rail with no stories", async () => {
    vi.mocked(getFollowRails).mockResolvedValue([rail({ stories: [], total: 0, new_count: 0 })]);
    render(<FollowRails />);
    expect(await screen.findByText(/we're watching/i)).toBeInTheDocument();
  });

  it("the section '+' routes to the create page", async () => {
    vi.mocked(getFollowRails).mockResolvedValue([rail()]);
    render(<FollowRails />);
    await userEvent.click(await screen.findByLabelText("Follow a new topic"));
    expect(push).toHaveBeenCalledWith("/follow/new");
  });
});
