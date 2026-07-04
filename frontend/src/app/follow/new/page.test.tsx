// WS-2 (#112): the "Follow anything" create page.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/api", () => ({
  addFollow: vi.fn(),
  getTopics: vi.fn().mockResolvedValue({ trending_topics: [{ id: 1, name: "AI" }], explore_topics: [] }),
}));

import FollowNewPage from "./page";
import { addFollow } from "@/lib/api";

describe("FollowNewPage", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.mocked(addFollow).mockReset().mockResolvedValue({ id: 5, kind: "saved_search", value: "x" });
  });

  it("disables Follow until a phrase is entered, then creates + lands on /following", async () => {
    render(<FollowNewPage />);
    const btn = screen.getByRole("button", { name: "Follow" });
    expect(btn).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Topic to follow"), "US Iran war");
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    await waitFor(() => expect(addFollow).toHaveBeenCalledWith("saved_search", "US Iran war"));
    expect(replace).toHaveBeenCalledWith("/following");
  });

  it("a trending chip creates that follow directly", async () => {
    render(<FollowNewPage />);
    await userEvent.click(await screen.findByText("AI"));
    await waitFor(() => expect(addFollow).toHaveBeenCalledWith("saved_search", "AI"));
  });

  it("surfaces the cap error inline (400), not a crash", async () => {
    vi.mocked(addFollow).mockRejectedValue(new Error("API 400: Bad Request"));
    render(<FollowNewPage />);
    await userEvent.type(screen.getByLabelText("Topic to follow"), "too many");
    await userEvent.click(screen.getByRole("button", { name: "Follow" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/maximum number of topics/i);
    expect(replace).not.toHaveBeenCalled();
  });
});
