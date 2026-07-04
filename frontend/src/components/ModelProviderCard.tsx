"use client";

/**
 * WS-6 (#116): the ONE provider card. Chips pick a provider (selection is local — nothing persists on
 * tap; Save confirms it as active), each provider has its own model input + API key field (masked
 * last-4), Save auto-runs the connection test, and a key can be removed per provider. Gemini is
 * primary — it's the default provider and powers embeddings. Replaces the old split "AI Configuration"
 * (OpenAI) card + the ProfileFields Gemini block.
 */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import {
  getSettings,
  setAnthropicKey,
  setGeminiKey,
  testAnthropicKey,
  testApiKey,
  testGeminiKey,
  updateSettings,
  type KeyTestResult,
  type UserSettings,
} from "@/lib/api";

type Provider = {
  id: string;
  label: string;
  models: string[];
  placeholder: string;
  saveKey: (v: string | null) => Promise<unknown>;
  test: () => Promise<KeyTestResult>;
  has: (s: UserSettings) => boolean;
  last4: (s: UserSettings) => string | null;
};

// Gemini first — the primary (default provider + embeddings).
const PROVIDERS: Provider[] = [
  {
    id: "gemini", label: "Gemini", models: ["gemini-2.0-flash", "gemini-2.5-pro"], placeholder: "AIza…",
    saveKey: (v) => setGeminiKey(v), test: testGeminiKey,
    has: (s) => s.has_gemini_key, last4: (s) => s.gemini_key_last4,
  },
  {
    id: "openai", label: "OpenAI", models: ["gpt-4o-mini", "gpt-4o"], placeholder: "sk-…",
    saveKey: (v) => updateSettings({ openai_api_key: v }), test: testApiKey,
    has: (s) => s.has_openai_key, last4: (s) => s.openai_key_last4,
  },
  {
    id: "anthropic", label: "Anthropic", models: ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"],
    placeholder: "sk-ant-…", saveKey: (v) => setAnthropicKey(v), test: testAnthropicKey,
    has: (s) => s.has_anthropic_key, last4: (s) => s.anthropic_key_last4,
  },
];

export function ModelProviderCard() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [selected, setSelected] = useState("gemini"); // local pick; persisted only on Save
  const [model, setModel] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function refresh() {
    const s = await getSettings();
    setSettings(s);
    return s;
  }

  // Default provider from GET /settings (fallback GEMINI, not openai — matched to the backend default).
  useEffect(() => {
    refresh()
      .then((s) => {
        const p = s.active_provider || "gemini";
        setSelected(p);
        setModel((s.model_prefs && s.model_prefs[p]) || "");
      })
      .catch(() => {});
  }, []);

  function pick(p: string) {
    setSelected(p);
    setModel((settings?.model_prefs && settings.model_prefs[p]) || "");
    setKeyInput("");
    setMsg(null);
  }

  const cur = PROVIDERS.find((p) => p.id === selected) ?? PROVIDERS[0];

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      // Confirm the provider choice + its model (save on confirm, not on chip tap).
      await updateSettings({ active_provider: selected, model_prefs: { [selected]: model.trim() } });
      // If a key was entered, save it and AUTO-RUN the connection test.
      if (keyInput.trim()) {
        await cur.saveKey(keyInput.trim());
        const res = await cur.test();
        setMsg({ ok: res.success, text: res.success ? "Saved · key verified" : res.error || "Couldn't verify key" });
        if (res.success) setKeyInput("");
      } else {
        setMsg({ ok: true, text: `${cur.label} is now your provider` });
      }
      await refresh();
    } catch {
      setMsg({ ok: false, text: "Couldn't save — try again" });
    } finally {
      setBusy(false);
    }
  }

  async function removeKey() {
    setBusy(true);
    setMsg(null);
    try {
      await cur.saveKey(null);
      setKeyInput("");
      setMsg({ ok: true, text: `${cur.label} key removed` });
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  const activeProvider = settings?.active_provider || "gemini";

  return (
    <Card variant="raised">
      <div className="p-3.5">
        <h2 className="text-h3 text-[var(--text-primary)]">Model provider</h2>
        <p className="text-small text-[var(--text-secondary)] mt-1">
          Gemini is the default provider. Add your own key to use your own quota or a specific model,
          or switch to another provider.
        </p>
        <p className="text-mono text-[var(--text-ghost)] mt-1">
          Optional — NewsLens includes built-in AI, no key needed.
        </p>

        <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Provider">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              type="button"
              aria-pressed={selected === p.id}
              onClick={() => pick(p.id)}
              disabled={busy}
              className={cn(
                "text-mono px-3 py-1.5 rounded-full border transition-colors disabled:opacity-50",
                selected === p.id
                  ? "border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--text-secondary)]"
              )}
            >
              {p.label}
              {activeProvider === p.id && (
                <span className="ml-1.5 text-[var(--text-ghost)]" aria-label="active provider">
                  ·&nbsp;active
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-2">
          <label className="text-small text-[var(--text-secondary)]" htmlFor="mp-model">
            Model for {cur.label}
          </label>
          <Input id="mp-model" value={model} onChange={(e) => setModel(e.target.value)} placeholder={cur.models[0]} />
          <p className="text-mono text-[var(--text-tertiary)]">e.g. {cur.models.join(" · ")}</p>
        </div>

        <div className="mt-4 space-y-2">
          <label className="text-small text-[var(--text-secondary)]" htmlFor="mp-key">
            {cur.label} API key
            {settings && cur.has(settings) ? ` — saved ····${cur.last4(settings) ?? ""}` : ""}
          </label>
          <Input
            id="mp-key"
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder={cur.placeholder}
            aria-label={`${cur.label} API key`}
          />
          <div className="flex gap-2">
            <Button onClick={save} disabled={busy} loading={busy}>
              Save
            </Button>
            {settings && cur.has(settings) && (
              <Button variant="ghost" onClick={removeKey} disabled={busy}>
                Remove key
              </Button>
            )}
          </div>
          {msg && (
            <p role="status" className={cn("text-small", msg.ok ? "text-[var(--accent)]" : "text-[var(--dismiss)]")}>
              {msg.text}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
