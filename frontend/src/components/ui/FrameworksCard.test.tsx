import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FrameworksCard } from "./FrameworksCard";
import type { FrameworksResult } from "@/lib/api";

const data: FrameworksResult = {
  story_type: "markets",
  frameworks: [
    { id: "base_rate", label: "Base rate", one_liner: "Open models have closed gaps before." },
    { id: "second_order", label: "2nd-order", one_liner: "Cheaper inference shifts chip demand." },
  ],
};

describe("FrameworksCard (Wave B2)", () => {
  it("renders the framework chips", () => {
    render(<FrameworksCard clusterId={1} data={data} />);
    expect(screen.getByText("Base rate")).toBeInTheDocument();
    expect(screen.getByText("2nd-order")).toBeInTheDocument();
  });

  it("reveals the one-liner when a chip is tapped", async () => {
    render(<FrameworksCard clusterId={1} data={data} />);
    await userEvent.click(screen.getByText("Base rate"));
    expect(await screen.findByText(/closed gaps before/i)).toBeInTheDocument();
  });

  it("renders nothing when no frameworks fire", () => {
    const { container } = render(<FrameworksCard clusterId={1} data={{ frameworks: [] }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
