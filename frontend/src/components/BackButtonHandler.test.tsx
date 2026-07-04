// WS-4 (#114): Android hardware back — pop / hop-to-Today / double-press-exit, native-gated.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";

let native = true;
let mockPath = "/";
const back = vi.fn();
const replace = vi.fn();
const minimizeApp = vi.fn();
let backCb: ((e: { canGoBack: boolean }) => void) | null = null;
const addListener = vi.fn(async (_ev: string, cb: (e: { canGoBack: boolean }) => void) => {
  backCb = cb;
  return { remove: vi.fn() };
});

vi.mock("@capacitor/core", () => ({ Capacitor: { isNativePlatform: () => native } }));
vi.mock("@capacitor/app", () => ({ App: { addListener, minimizeApp } }));
vi.mock("next/navigation", () => ({ usePathname: () => mockPath, useRouter: () => ({ back, replace }) }));

import { BackButtonHandler } from "./BackButtonHandler";

async function press(canGoBack: boolean) {
  await act(async () => {
    backCb?.({ canGoBack });
    await Promise.resolve();
  });
}

beforeEach(() => {
  native = true;
  mockPath = "/";
  backCb = null;
  back.mockReset();
  replace.mockReset();
  minimizeApp.mockReset();
  addListener.mockClear();
});

describe("BackButtonHandler (WS-4 Android back)", () => {
  it("web: registers NO back listener (stock browser back)", async () => {
    native = false;
    render(<BackButtonHandler />);
    await Promise.resolve();
    expect(addListener).not.toHaveBeenCalled();
  });

  it("a stacked non-root route with history pops", async () => {
    mockPath = "/story/5";
    render(<BackButtonHandler />);
    await waitFor(() => expect(addListener).toHaveBeenCalled());
    await press(true);
    expect(back).toHaveBeenCalledTimes(1);
    expect(replace).not.toHaveBeenCalled();
    expect(minimizeApp).not.toHaveBeenCalled();
  });

  it("a non-home tab root hops to Today (one replace)", async () => {
    mockPath = "/discover";
    render(<BackButtonHandler />);
    await waitFor(() => expect(addListener).toHaveBeenCalled());
    await press(true);
    expect(replace).toHaveBeenCalledWith("/");
    expect(back).not.toHaveBeenCalled();
  });

  it("home: first back shows the exit toast; second within the window minimizes (never exits)", async () => {
    mockPath = "/";
    render(<BackButtonHandler />);
    await waitFor(() => expect(addListener).toHaveBeenCalled());

    await press(false);
    expect(await screen.findByText(/press back again to exit/i)).toBeInTheDocument();
    expect(minimizeApp).not.toHaveBeenCalled();

    await press(false);
    expect(minimizeApp).toHaveBeenCalledTimes(1);
    expect(back).not.toHaveBeenCalled();
  });

  it("disarms the exit gesture on navigation (no single-press minimize after a hop)", async () => {
    // Regression (WS-4 review): the armed exit flag must not leak across routes. Arm on home, hop
    // away and back, then a single press must RE-ARM (toast), not minimize.
    mockPath = "/";
    const { rerender } = render(<BackButtonHandler />);
    await waitFor(() => expect(addListener).toHaveBeenCalled());

    await press(false); // arm on home
    expect(minimizeApp).not.toHaveBeenCalled();

    mockPath = "/discover"; // navigate away → disarm
    rerender(<BackButtonHandler />);
    mockPath = "/"; // and back home
    rerender(<BackButtonHandler />);

    await press(false); // single press on home → must re-arm, NOT minimize
    expect(minimizeApp).not.toHaveBeenCalled();
  });

  it("a deep-linked route with NO history takes the exit path, never pops", async () => {
    mockPath = "/story/5";
    render(<BackButtonHandler />);
    await waitFor(() => expect(addListener).toHaveBeenCalled());

    await press(false); // cold-start deep link → no history
    expect(await screen.findByText(/press back again to exit/i)).toBeInTheDocument();
    expect(back).not.toHaveBeenCalled();

    await press(false);
    expect(minimizeApp).toHaveBeenCalledTimes(1);
  });
});
