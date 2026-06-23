import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgreementMeter } from "./AgreementMeter";

const base = { coherence: 0.88, sourceCount: 7, createdAt: "2026-06-24T00:00:00Z" };

describe("AgreementMeter (Wave A honest relabel)", () => {
  it("no longer claims 'Sources agree' (regression)", () => {
    render(<AgreementMeter {...base} />);
    expect(screen.queryByText(/sources agree/i)).toBeNull();
  });

  it("shows the honest 'Source overlap' label + percentage", () => {
    render(<AgreementMeter {...base} />);
    expect(screen.getByText(/source overlap/i)).toBeInTheDocument();
    expect(screen.getByText("88%")).toBeInTheDocument();
  });
});
