import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

let mockPath = "/";
const back = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => mockPath,
  useRouter: () => ({ back }),
}));

import { NavBar } from "./NavBar";

beforeEach(() => back.mockReset());

// WS-4 (#114): the shared NavBar renders a back control on non-root (deep-dive) routes and calls
// router.back(); tab roots get NO back header (the tab bar is their navigation).
describe("NavBar back control (WS-4)", () => {
  it("renders a back control on a non-root deep-dive route and pops on tap", async () => {
    mockPath = "/story/5";
    render(<NavBar />);
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(back).toHaveBeenCalledTimes(1);
  });

  it("shows NO back header on a tab root (logo instead)", () => {
    mockPath = "/discover";
    render(<NavBar />);
    expect(screen.queryByRole("button", { name: /back/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/NewsLens home/i)).toBeInTheDocument();
  });
});

describe("NavBar feed entry (#100)", () => {
  it("shows a Feed link pointing at /feed alongside Search", () => {
    mockPath = "/";
    render(<NavBar />);
    const feed = screen.getByRole("link", { name: /feed/i });
    expect(feed).toHaveAttribute("href", "/feed");
    expect(screen.getByRole("link", { name: /search/i })).toHaveAttribute("href", "/search");
  });

  it("marks the Feed link current when on /feed", () => {
    mockPath = "/feed";
    render(<NavBar />);
    expect(screen.getByRole("link", { name: /feed/i })).toHaveAttribute("aria-current", "page");
  });
});
