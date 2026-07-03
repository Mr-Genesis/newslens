import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

let mockPath = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPath,
  useRouter: () => ({ back: vi.fn() }),
}));

import { NavBar } from "./NavBar";

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
