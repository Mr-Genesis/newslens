import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourceTierBadge } from "./SourceTierBadge";

describe("SourceTierBadge (Phase 2 · #78)", () => {
  it("shows a RESEARCH badge for a research source", () => {
    render(<SourceTierBadge sourceType="research" />);
    expect(screen.getByText("RESEARCH")).toBeInTheDocument();
  });

  it("shows EXPERT with author and credibility score", () => {
    render(
      <SourceTierBadge sourceType="expert" authorName="Ben Thompson" credibilityScore={88} />
    );
    expect(screen.getByText("EXPERT")).toBeInTheDocument();
    expect(screen.getByText(/Ben Thompson/)).toBeInTheDocument();
    expect(screen.getByText(/88/)).toBeInTheDocument();
  });

  it("adds a PREPRINT · not peer-reviewed badge for preprints", () => {
    render(<SourceTierBadge sourceType="research" isPreprint />);
    expect(screen.getByText("PREPRINT")).toBeInTheDocument();
    expect(screen.getByText(/not peer-reviewed/)).toBeInTheDocument();
  });

  it("renders nothing for a plain news source", () => {
    const { container } = render(<SourceTierBadge sourceType="wire" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the tier is unknown/null", () => {
    const { container } = render(<SourceTierBadge sourceType={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows an OFFICIAL badge for an official (regulator/gov) source", () => {
    render(<SourceTierBadge sourceType="official" />);
    expect(screen.getByText("OFFICIAL")).toBeInTheDocument();
  });

  it("shows a FILING badge for a per-company disclosure source", () => {
    render(<SourceTierBadge sourceType="filing" />);
    expect(screen.getByText("FILING")).toBeInTheDocument();
  });
});
