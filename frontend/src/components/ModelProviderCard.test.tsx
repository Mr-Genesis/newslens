import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const BASE = {
  has_openai_key: false, openai_key_verified: false, openai_key_last4: null, openai_key_verified_at: null,
  has_gemini_key: false, gemini_key_verified: false, gemini_key_last4: null, gemini_key_verified_at: null,
  has_anthropic_key: false, anthropic_key_verified: false, anthropic_key_last4: null,
  anthropic_key_verified_at: null, active_provider: "openai", model_prefs: {},
};

vi.mock("@/lib/api", () => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn().mockResolvedValue({}),
  setAnthropicKey: vi.fn().mockResolvedValue({ has_anthropic_key: true }),
  testAnthropicKey: vi.fn().mockResolvedValue({ success: true, error: null, models_available: 1 }),
}));

import { ModelProviderCard } from "./ModelProviderCard";
import * as api from "@/lib/api";

beforeEach(() => {
  vi.mocked(api.getSettings).mockResolvedValue({ ...BASE });
  vi.mocked(api.updateSettings).mockClear();
});

describe("ModelProviderCard (Wave E)", () => {
  it("renders the three providers", async () => {
    render(<ModelProviderCard />);
    expect(await screen.findByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    expect(screen.getByText("Gemini")).toBeInTheDocument();
  });

  it("selecting a provider persists active_provider", async () => {
    render(<ModelProviderCard />);
    await userEvent.click(await screen.findByText("Anthropic"));
    await waitFor(() =>
      expect(vi.mocked(api.updateSettings)).toHaveBeenCalledWith({ active_provider: "anthropic" })
    );
  });

  it("shows the Anthropic key field when Anthropic is active", async () => {
    vi.mocked(api.getSettings).mockResolvedValue({ ...BASE, active_provider: "anthropic" });
    render(<ModelProviderCard />);
    expect(await screen.findByPlaceholderText("sk-ant-...")).toBeInTheDocument();
  });
});
