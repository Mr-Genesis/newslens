import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({ addFollow: vi.fn() }));

import { DiscoverCard } from "./DiscoverCard";
import { addFollow } from "@/lib/api";
import type { DiscoverCard as DiscoverCardType } from "@/lib/api";

const gated: DiscoverCardType = {
  id: 1, article_id: 10, title: "AI preprint", tension_line: "AI preprint",
  facts: ["fact one"], sources: ["arXiv"], topic_id: 0, topic_name: "technology",
  coherence: 0.8, source_id: 9, source_type: "expert", is_gated: true,
  is_preprint: false, author_name: "Ethan Mollick", credibility_score: 92,
};
const news: DiscoverCardType = {
  ...gated, id: 2, title: "World news", sources: ["Reuters"],
  source_id: 3, source_type: "wire", is_gated: false, author_name: null, credibility_score: null,
};

describe("DiscoverCard gated opt-in (Phase 2 · #78/#83)", () => {
  beforeEach(() => vi.mocked(addFollow).mockResolvedValue({ id: 1, kind: "source", value: "9" }));

  it("badges a gated card and offers Follow source", async () => {
    render(<DiscoverCard card={gated} onSwipe={() => {}} isTop stackIndex={0} />);
    expect(screen.getByText("EXPERT")).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: /follow source/i });
    await userEvent.click(btn);
    expect(addFollow).toHaveBeenCalledWith("source", "9");
  });

  it("shows no follow affordance or tier badge for a news card", () => {
    render(<DiscoverCard card={news} onSwipe={() => {}} isTop stackIndex={0} />);
    expect(screen.queryByRole("button", { name: /follow source/i })).toBeNull();
    expect(screen.queryByText("EXPERT")).toBeNull();
    expect(screen.queryByText("RESEARCH")).toBeNull();
  });
});
