import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({
  askStory: vi.fn(),
  isAskAnswer: (r: unknown) => !!r && !("unavailable" in (r as object)),
}));

import { AskBox } from "./AskBox";
import { askStory } from "@/lib/api";

describe("AskBox (Wave B1)", () => {
  beforeEach(() => vi.mocked(askStory).mockReset());

  it("renders the ask input", () => {
    render(<AskBox clusterId={1} />);
    expect(screen.getByPlaceholderText(/ask about this story/i)).toBeInTheDocument();
  });

  it("shows the grounded answer and its citation after asking", async () => {
    vi.mocked(askStory).mockResolvedValue({
      answer: "The EU passed the AI Act.",
      citations: [{ claim: "x", source: "Reuters" }],
      refused: false,
    });
    render(<AskBox clusterId={1} />);
    await userEvent.type(screen.getByPlaceholderText(/ask about this story/i), "What happened?");
    await userEvent.click(screen.getByRole("button", { name: /ask/i }));
    expect(await screen.findByText(/the eu passed the ai act/i)).toBeInTheDocument();
    expect(screen.getByText(/Reuters/)).toBeInTheDocument();
  });

  it("shows a refusal message when the answer isn't in the sources", async () => {
    vi.mocked(askStory).mockResolvedValue({ answer: "", citations: [], refused: true });
    render(<AskBox clusterId={1} />);
    await userEvent.type(screen.getByPlaceholderText(/ask about this story/i), "Who won?");
    await userEvent.click(screen.getByRole("button", { name: /ask/i }));
    expect(await screen.findByText(/not.*sources/i)).toBeInTheDocument();
  });
});
