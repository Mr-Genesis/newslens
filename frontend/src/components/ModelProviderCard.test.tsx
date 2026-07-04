// WS-6 (#116): the unified provider card — chips (save on confirm), per-provider model + key,
// Save auto-runs Test, Remove per provider, default provider from settings (Gemini fallback).
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const BASE = {
  has_openai_key: false, openai_key_verified: false, openai_key_last4: null, openai_key_verified_at: null,
  has_gemini_key: false, gemini_key_verified: false, gemini_key_last4: null, gemini_key_verified_at: null,
  has_anthropic_key: false, anthropic_key_verified: false, anthropic_key_last4: null,
  anthropic_key_verified_at: null, active_provider: "gemini", model_prefs: {},
};

vi.mock("@/lib/api", () => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn().mockResolvedValue({}),
  setGeminiKey: vi.fn().mockResolvedValue({}),
  testGeminiKey: vi.fn().mockResolvedValue({ success: true, error: null, models_available: 1 }),
  setAnthropicKey: vi.fn().mockResolvedValue({}),
  testAnthropicKey: vi.fn().mockResolvedValue({ success: true, error: null, models_available: 1 }),
  testApiKey: vi.fn().mockResolvedValue({ success: true, error: null, models_available: 1 }),
}));

import { ModelProviderCard } from "./ModelProviderCard";
import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getSettings).mockResolvedValue({ ...BASE });
});

describe("ModelProviderCard (WS-6 unified)", () => {
  it("renders all three providers and defaults to the active provider (Gemini)", async () => {
    render(<ModelProviderCard />);
    expect(await screen.findByRole("button", { name: /Gemini/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /OpenAI/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Anthropic/ })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Gemini/ })).toHaveAttribute("aria-pressed", "true")
    );
  });

  it("a chip tap selects locally and does NOT persist (save on confirm)", async () => {
    render(<ModelProviderCard />);
    await userEvent.click(await screen.findByRole("button", { name: /OpenAI/ }));
    expect(screen.getByRole("button", { name: /OpenAI/ })).toHaveAttribute("aria-pressed", "true");
    expect(api.updateSettings).not.toHaveBeenCalled(); // nothing persisted until Save
  });

  it("Save confirms the provider + model and auto-runs the key test", async () => {
    render(<ModelProviderCard />);
    await screen.findByRole("button", { name: /Gemini/ });
    await userEvent.type(screen.getByLabelText("Gemini API key"), "AIza-newkey");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({ active_provider: "gemini" })
      )
    );
    expect(api.setGeminiKey).toHaveBeenCalledWith("AIza-newkey"); // key saved
    expect(api.testGeminiKey).toHaveBeenCalled();                  // …and auto-tested
    expect(await screen.findByText(/verified/i)).toBeInTheDocument();
  });

  it("removes a saved key per provider", async () => {
    vi.mocked(api.getSettings).mockResolvedValue({
      ...BASE, active_provider: "gemini", has_gemini_key: true, gemini_key_last4: "beef",
    });
    render(<ModelProviderCard />);
    await userEvent.click(await screen.findByRole("button", { name: /Remove key/ }));
    expect(api.setGeminiKey).toHaveBeenCalledWith(null);
  });
});
