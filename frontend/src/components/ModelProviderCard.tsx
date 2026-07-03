"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import {
  getSettings,
  setAnthropicKey,
  testAnthropicKey,
  updateSettings,
  type KeyTestResult,
  type UserSettings,
} from "@/lib/api";

// Curated, current model ids per provider (free-text field — these are hints/defaults). Wave E.
const PROVIDERS = [
  { id: "openai", label: "OpenAI", models: ["gpt-4o-mini", "gpt-4o"] },
  { id: "anthropic", label: "Anthropic", models: ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"] },
  { id: "gemini", label: "Gemini", models: ["gemini-2.0-flash", "gemini-2.5-pro"] },
];

/** Wave E "Bring Your Own Model": choose the active provider + per-provider model, and manage the
 *  Anthropic key. (OpenAI key card + Gemini key live in their existing controls.) */
export function ModelProviderCard() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("");
  const [anthKey, setAnthKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState<KeyTestResult | null>(null);

  async function refresh() {
    const s = await getSettings();
    setSettings(s);
    const p = s.active_provider || "openai";
    setProvider(p);
    setModel((s.model_prefs && s.model_prefs[p]) || "");
  }

  useEffect(() => {
    refresh().catch(() => {});
  }, []);

  async function selectProvider(p: string) {
    setProvider(p);
    setModel((settings?.model_prefs && settings.model_prefs[p]) || "");
    setTest(null);
    setBusy(true);
    try {
      await updateSettings({ active_provider: p });
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function saveModel() {
    setBusy(true);
    try {
      await updateSettings({ model_prefs: { [provider]: model.trim() } });
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function saveAnthKey() {
    setBusy(true);
    try {
      await setAnthropicKey(anthKey.trim() || null);
      setAnthKey("");
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function runTest() {
    setBusy(true);
    try {
      setTest(await testAnthropicKey());
    } finally {
      setBusy(false);
    }
  }

  const cur = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0];

  return (
    <Card variant="raised">
      <div className="p-3.5">
      <h2 className="text-h3 text-[var(--text-primary)]">Model provider</h2>
      <p className="text-small text-[var(--text-secondary)] mt-1">
        Which AI provider + model powers summaries, lenses, and entity extraction.
      </p>
      <p className="text-mono text-[var(--text-ghost)] mt-1">
        Optional — NewsLens includes built-in AI, no key needed. Add your own key only to use
        your own quota or a specific model.
      </p>

      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Provider">
        {PROVIDERS.map((p) => (
          <button
            key={p.id}
            type="button"
            aria-pressed={provider === p.id}
            onClick={() => selectProvider(p.id)}
            disabled={busy}
            className={cn(
              "text-mono px-3 py-1.5 rounded-full border transition-colors disabled:opacity-50",
              provider === p.id
                ? "border-[var(--accent-muted)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                : "border-[var(--border)] text-[var(--text-secondary)]"
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-2">
        <label className="text-small text-[var(--text-secondary)]">Model for {cur.label}</label>
        <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder={cur.models[0]} />
        <p className="text-mono text-[var(--text-tertiary)]">e.g. {cur.models.join(" · ")}</p>
        <Button onClick={saveModel} disabled={busy}>Save model</Button>
      </div>

      {provider === "anthropic" && (
        <div className="mt-5 space-y-2 border-t border-[var(--border)] pt-4">
          <label className="text-small text-[var(--text-secondary)]">
            Anthropic API key
            {settings?.has_anthropic_key ? ` — saved ····${settings.anthropic_key_last4 ?? ""}` : ""}
          </label>
          <Input type="password" value={anthKey} onChange={(e) => setAnthKey(e.target.value)} placeholder="sk-ant-..." />
          <div className="flex gap-2">
            <Button onClick={saveAnthKey} disabled={busy}>Save key</Button>
            <Button onClick={runTest} disabled={busy || !settings?.has_anthropic_key}>Test connection</Button>
          </div>
          {test && (
            <p className={cn("text-small", test.success ? "text-[var(--accent)]" : "text-red-400")}>
              {test.success ? "Key works." : test.error}
            </p>
          )}
        </div>
      )}
      </div>
    </Card>
  );
}
