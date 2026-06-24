import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const push = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace }) }));

import WelcomePage from "./page";

describe("Welcome — first-run intro carousel", () => {
  beforeEach(() => {
    localStorage.clear();
    push.mockClear();
    replace.mockClear();
  });

  it("opens on page 1 with Skip + Next and no Back", () => {
    render(<WelcomePage />);
    expect(screen.getByText(/ten headlines/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /skip/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /next/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /back/i })).toBeNull();
  });

  it("advances to the last page where Next/Skip give way to Back + Get started", async () => {
    render(<WelcomePage />);
    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.queryByRole("button", { name: /next/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /skip/i })).toBeNull();
    expect(screen.getByRole("button", { name: /back/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /get started/i }));
    expect(push).toHaveBeenCalledWith("/onboarding");
  });

  it("Skip hands off to the topic picker", async () => {
    render(<WelcomePage />);
    await userEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(push).toHaveBeenCalledWith("/onboarding");
  });

  it("bounces already-onboarded users to the app", () => {
    localStorage.setItem("newslens-onboarded", "1");
    render(<WelcomePage />);
    expect(replace).toHaveBeenCalledWith("/");
  });
});
