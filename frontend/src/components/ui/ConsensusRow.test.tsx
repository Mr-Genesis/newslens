import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConsensusRow } from "./ConsensusRow";

describe("ConsensusRow (Wave B3)", () => {
  it("shows the align count", () => {
    render(<ConsensusRow clusterId={1} data={{ agree_count: 6, total: 7, dissent: [] }} />);
    expect(screen.getByText(/6 of 7 align/i)).toBeInTheDocument();
  });

  it("names the dissenter under WHERE THEY DIVERGE", () => {
    render(
      <ConsensusRow
        clusterId={1}
        data={{
          agree_count: 6,
          total: 7,
          dissent: [{ outlet: "Ars Technica", point: "parity unproven" }],
        }}
      />
    );
    expect(screen.getByText(/where they diverge/i)).toBeInTheDocument();
    expect(screen.getByText(/Ars Technica/)).toBeInTheDocument();
  });

  it("renders nothing when unavailable", () => {
    const { container } = render(<ConsensusRow clusterId={1} data={{ unavailable: true }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
