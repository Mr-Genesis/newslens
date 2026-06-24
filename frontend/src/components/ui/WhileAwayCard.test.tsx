import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ getDigest: vi.fn() }));

import { WhileAwayCard } from "./WhileAwayCard";
import { getDigest } from "@/lib/api";

describe("WhileAwayCard (Wave C)", () => {
  beforeEach(() => vi.mocked(getDigest).mockReset());

  it("renders the digest items when something moved", async () => {
    vi.mocked(getDigest).mockResolvedValue({
      count: 2,
      since: "2026-06-23T00:00:00Z",
      items: [
        { cluster_id: 1, title: "Story One", headline: "Touches your work." },
        { cluster_id: 2, title: "Story Two", headline: null },
      ],
    });
    render(<WhileAwayCard />);
    expect(await screen.findByText(/while you were away/i)).toBeInTheDocument();
    expect(screen.getByText("Story One")).toBeInTheDocument();
    expect(screen.getByText("Touches your work.")).toBeInTheDocument();
  });

  it("renders nothing when caught up", async () => {
    vi.mocked(getDigest).mockResolvedValue({ count: 0, since: "x", items: [] });
    const { container } = render(<WhileAwayCard />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
