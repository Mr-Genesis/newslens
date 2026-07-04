// WS-4 (#114): bottom-tab navigation uses router.replace on native (tabs never stack history) so
// hardware back can't walk through every prior tab switch; web keeps stock Link push semantics.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const replace = vi.fn();
const push = vi.fn();
let native = false;
let mockPath = "/";

vi.mock("next/navigation", () => ({
  usePathname: () => mockPath,
  useRouter: () => ({ replace, push }),
}));
vi.mock("@capacitor/core", () => ({ Capacitor: { isNativePlatform: () => native } }));

import { BottomTabBar } from "./BottomTabBar";

beforeEach(() => {
  replace.mockReset();
  push.mockReset();
  native = false;
  mockPath = "/";
});

describe("BottomTabBar tab-nav history (WS-4)", () => {
  it("on web, a tab tap does NOT force router.replace (Link handles the push)", async () => {
    native = false;
    render(<BottomTabBar />);
    await userEvent.click(screen.getByRole("link", { name: /Discover/i }));
    expect(replace).not.toHaveBeenCalled();
  });

  it("on native, a tab tap uses router.replace (no history stacking)", async () => {
    native = true;
    render(<BottomTabBar />);
    await userEvent.click(screen.getByRole("link", { name: /Discover/i }));
    expect(replace).toHaveBeenCalledWith("/discover");
    expect(push).not.toHaveBeenCalled();
  });

  it("on native, tapping the CURRENT tab is a no-op (no replace to self)", async () => {
    native = true;
    mockPath = "/";
    render(<BottomTabBar />);
    await userEvent.click(screen.getByRole("link", { name: /Today/i }));
    expect(replace).not.toHaveBeenCalled();
  });
});
