import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LaunchScreen } from "./LaunchScreen";

describe("LaunchScreen — cold-start experience", () => {
  it("frames the wait as progress, not a dead screen", () => {
    render(<LaunchScreen onRetry={vi.fn()} />);
    expect(
      screen.getByText(/preparing your first briefing/i)
    ).toBeInTheDocument();
    // At least one pipeline step label is visible.
    expect(screen.getByText(/gathering reports/i)).toBeInTheDocument();
  });

  it("lets an impatient reader force a re-check", async () => {
    const onRetry = vi.fn();
    render(<LaunchScreen onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /check now/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
