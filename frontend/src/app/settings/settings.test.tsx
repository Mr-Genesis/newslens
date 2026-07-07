// Unify A / adversarial-review finding 7 (HIGH): the Settings topic toggle must operate on the
// user's REAL server interests, never the stale localStorage / hardcoded-defaults set — otherwise one
// tap on a fresh device (empty localStorage → 8 defaults) full-replaces and WIPES curated interests +
// topic follows.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";

vi.mock("next/link", () => ({ default: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/components/ThemeProvider", () => ({
  useTheme: () => ({ theme: "dark", setTheme: vi.fn() }),
}));
vi.mock("@/components/ProfileFields", () => ({ ProfileFields: () => null }));
vi.mock("@/components/ModelProviderCard", () => ({ ModelProviderCard: () => null }));
vi.mock("@/components/AccountCard", () => ({ AccountCard: () => null }));
vi.mock("@/components/SystemCard", () => ({ SystemCard: () => null }));
vi.mock("@/lib/api", () => ({
  getStats: vi.fn().mockResolvedValue(null),
  getTopics: vi.fn(),
  updateProfile: vi.fn().mockResolvedValue(undefined),
}));

import ProfilePage from "./page";
import { getTopics, updateProfile } from "@/lib/api";

const topic = (name: string) => ({ id: name, name, article_count: 5 });

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear(); // fresh device: no persisted topics → the buggy path would fall back to defaults
});

describe("Settings topic toggle (finding 7)", () => {
  it("toggling a topic off PUTs the server set minus that topic — never the stale hardcoded defaults", async () => {
    vi.mocked(getTopics).mockResolvedValue({
      your_topics: [topic("Physics"), topic("Fusion Energy"), topic("Quantum Computing")],
      explore_topics: [],
      trending_topics: [],
    });

    render(<ProfilePage />);
    await userEvent.click(await screen.findByText("Physics")); // toggle OFF Physics

    await waitFor(() => expect(updateProfile).toHaveBeenCalled());
    const sent = vi.mocked(updateProfile).mock.calls[0][0].interests ?? [];
    expect(new Set(sent)).toEqual(new Set(["Fusion Energy", "Quantum Computing"])); // kept the rest
    expect(sent).not.toContain("Technology"); // did NOT resurrect the hardcoded defaults
    expect(sent).not.toContain("Physics"); // removed the one tapped
  });

  it("toggling a topic on (no prior interests) PUTs only that topic, not the 8 defaults", async () => {
    vi.mocked(getTopics).mockResolvedValue({
      your_topics: [], // brand-new user, zero interests → chips fall back to the default catalog
      explore_topics: [],
      trending_topics: [],
    });

    render(<ProfilePage />);
    await userEvent.click(await screen.findByText("Technology")); // pick one default

    await waitFor(() => expect(updateProfile).toHaveBeenCalled());
    const sent = vi.mocked(updateProfile).mock.calls[0][0].interests ?? [];
    expect(sent).toEqual(["Technology"]); // exactly the one chosen, not all 8 defaults
  });
});
