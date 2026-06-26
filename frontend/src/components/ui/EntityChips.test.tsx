import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EntityChips } from "./EntityChips";
import type { ClusterEntity } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getClusterEntities: vi.fn(),
  getEntityClusters: vi
    .fn()
    .mockResolvedValue([{ cluster_id: 9, title: "Older related story", created_at: "x" }]),
  addFollow: vi.fn().mockResolvedValue({ id: 1, kind: "entity", value: "Reserve Bank" }),
}));

import * as api from "@/lib/api";

const entities: ClusterEntity[] = [
  { id: 1, canonical_name: "Reserve Bank", kind: "org", salience: 0.9 },
  { id: 2, canonical_name: "Geneva", kind: "place", salience: 0.5 },
];

describe("EntityChips (G1)", () => {
  it("renders a chip per entity", () => {
    render(<EntityChips clusterId={1} data={entities} />);
    expect(screen.getByText("Reserve Bank")).toBeInTheDocument();
    expect(screen.getByText("Geneva")).toBeInTheDocument();
  });

  it("renders nothing when there are no entities", () => {
    const { container } = render(<EntityChips clusterId={1} data={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the 'appears in' rail when a chip is tapped", async () => {
    render(<EntityChips clusterId={1} data={entities} />);
    await userEvent.click(screen.getByText("Reserve Bank"));
    expect(await screen.findByText("Older related story")).toBeInTheDocument();
  });

  it("Follow passes the entity id (G2)", async () => {
    render(<EntityChips clusterId={1} data={entities} />);
    await userEvent.click(screen.getByText("Reserve Bank"));
    await userEvent.click(await screen.findByText("Follow"));
    expect(vi.mocked(api.addFollow)).toHaveBeenCalledWith("entity", "Reserve Bank", 1);
  });
});
