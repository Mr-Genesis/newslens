import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// SourceCard renders a FollowButton, which self-fetches follows on mount.
vi.mock("@/lib/api", () => ({
  getFollows: vi.fn(),
  addFollow: vi.fn(),
  removeFollow: vi.fn(),
}));

import { SourceCard } from "./SourceCard";
import { getFollows } from "@/lib/api";

const base = {
  sourceName: "NEJM",
  url: "https://nejm.example/a",
  snippet: "A source excerpt.",
  isFree: true,
};

describe("SourceCard tier badges + follow (Phase 2 · #78/#81)", () => {
  beforeEach(() => vi.mocked(getFollows).mockResolvedValue([]));

  it("badges a research source and offers a source-follow", () => {
    render(<SourceCard {...base} sourceType="research" sourceId={7} isPreprint />);
    expect(screen.getByText("RESEARCH")).toBeInTheDocument();
    expect(screen.getByText("PREPRINT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /follow/i })).toBeInTheDocument();
  });

  it("badges an expert source with author + score", () => {
    render(
      <SourceCard {...base} sourceName="Stratechery" sourceType="expert"
        authorName="Ben Thompson" credibilityScore={88} sourceId={9} />
    );
    expect(screen.getByText("EXPERT")).toBeInTheDocument();
    expect(screen.getByText(/Ben Thompson/)).toBeInTheDocument();
    expect(screen.getByText(/88/)).toBeInTheDocument();
  });

  it("shows no tier badge and no follow control for a plain news source", () => {
    render(<SourceCard {...base} sourceName="Reuters" sourceType="wire" sourceId={3} />);
    expect(screen.queryByText("RESEARCH")).toBeNull();
    expect(screen.queryByText("EXPERT")).toBeNull();
    expect(screen.queryByRole("button", { name: /follow/i })).toBeNull();
  });
});
