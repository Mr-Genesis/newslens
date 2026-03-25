"use client";

import { useEffect, useState, useCallback } from "react";
import { NavBar } from "@/components/layout/NavBar";
import {
  getSettings,
  updateSettings,
  testApiKey,
  type UserSettings,
  type KeyTestResult,
} from "@/lib/api";
import { relativeTime } from "@/lib/utils";

type PageState = "loading" | "idle" | "editing" | "saving" | "testing";

export default function SettingsPage() {
  const [state, setState] = useState<PageState>("loading");
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<KeyTestResult | null>(null);

  const fetchSettings = useCallback(async () => {
    try {
      setState("loading");
      const data = await getSettings();
      setSettings(data);
      setState("idle");
    } catch {
      setError("Failed to load settings");
      setState("idle");
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleSave = async () => {
    if (!keyInput.trim()) return;
    try {
      setState("saving");
      setError(null);
      setTestResult(null);
      const data = await updateSettings({ openai_api_key: keyInput.trim() });
      setSettings(data);
      setKeyInput("");
      setShowKey(false);
      setState("idle");
    } catch {
      setError("Failed to save API key");
      setState("editing");
    }
  };

  const handleRemove = async () => {
    try {
      setState("saving");
      setError(null);
      setTestResult(null);
      const data = await updateSettings({ openai_api_key: null });
      setSettings(data);
      setKeyInput("");
      setState("idle");
    } catch {
      setError("Failed to remove API key");
      setState("idle");
    }
  };

  const handleTest = async () => {
    try {
      setState("testing");
      setError(null);
      const result = await testApiKey();
      setTestResult(result);
      // Re-fetch settings to get updated verification status
      const data = await getSettings();
      setSettings(data);
      setState("idle");
    } catch {
      setTestResult({ success: false, error: "Connection failed", models_available: 0 });
      setState("idle");
    }
  };

  const isEditing = state === "editing" || keyInput.length > 0;

  return (
    <>
      <NavBar />
      <main className="flex-1 mx-auto max-w-[640px] w-full px-[var(--space-md)] pb-[var(--page-bottom)]">
        <div className="pt-[var(--space-lg)]">
          <h1 className="text-hero text-[var(--text-primary)]">Settings</h1>
        </div>

        {/* Loading */}
        {state === "loading" && (
          <div className="mt-[var(--space-xl)]">
            <div className="skeleton h-[200px] w-full rounded-[var(--radius-md)]" />
          </div>
        )}

        {/* Settings form */}
        {state !== "loading" && (
          <div className="mt-[var(--space-xl)] max-w-[480px]">
            {/* Section: OpenAI API Key */}
            <div className="rounded-[var(--radius-md)] bg-[var(--surface)] border border-[var(--border)] p-[var(--space-lg)]">
              <h2 className="text-heading text-[var(--text-primary)]">
                OpenAI API Key
              </h2>
              <p className="text-small text-[var(--text-secondary)] mt-[var(--space-xs)]">
                Used for generating article embeddings and AI summaries.
                Without a key, articles are ingested but clustering and
                summaries are disabled.
              </p>

              {/* Current key status */}
              {settings?.has_openai_key && !isEditing && (
                <div className="mt-[var(--space-md)]">
                  <div className="flex items-center gap-[var(--space-sm)]">
                    <div className="flex-1 h-12 flex items-center px-[var(--space-md)] rounded-[var(--radius-md)] bg-[var(--surface-raised)] border border-[var(--border)]">
                      <span className="text-body text-[var(--text-muted)] tracking-wider">
                        {"••••••••••••" + (settings.openai_key_last4 || "****")}
                      </span>
                    </div>
                  </div>

                  <div className="flex gap-[var(--space-sm)] mt-[var(--space-md)]">
                    <button
                      onClick={() => {
                        setKeyInput("");
                        setState("editing");
                      }}
                      className="flex-1 h-12 rounded-[var(--radius-md)] bg-[var(--surface-raised)] text-small font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
                    >
                      Change Key
                    </button>
                    <button
                      onClick={handleRemove}
                      disabled={state === "saving"}
                      className="h-12 px-[var(--space-lg)] rounded-[var(--radius-md)] text-small font-medium text-[var(--dismiss)] hover:bg-[var(--dismiss-muted)] transition-colors disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}

              {/* Input field (shown when no key or editing) */}
              {(!settings?.has_openai_key || isEditing) && (
                <div className="mt-[var(--space-md)]">
                  <div className="relative">
                    <input
                      type={showKey ? "text" : "password"}
                      value={keyInput}
                      onChange={(e) => {
                        setKeyInput(e.target.value);
                        if (state !== "editing") setState("editing");
                      }}
                      placeholder="sk-..."
                      className="w-full h-12 px-[var(--space-md)] pr-12 rounded-[var(--radius-md)] bg-[var(--surface)] border border-[var(--border)] text-body text-[var(--text-primary)] placeholder:text-[var(--text-ghost)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2 focus:ring-offset-[var(--bg)] transition-shadow"
                      autoComplete="off"
                      spellCheck={false}
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey(!showKey)}
                      className="absolute right-0 top-0 h-12 w-12 flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
                      aria-label={showKey ? "Hide key" : "Show key"}
                    >
                      {showKey ? (
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                          <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                          <line x1="1" y1="1" x2="23" y2="23" />
                        </svg>
                      ) : (
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                      )}
                    </button>
                  </div>

                  <div className="flex gap-[var(--space-sm)] mt-[var(--space-md)]">
                    <button
                      onClick={handleSave}
                      disabled={!keyInput.trim() || state === "saving"}
                      className="flex-1 h-12 rounded-[var(--radius-md)] bg-[var(--accent)] text-small font-semibold text-[var(--gray-950)] hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {state === "saving" ? "Saving..." : "Save Key"}
                    </button>
                    {settings?.has_openai_key && (
                      <button
                        onClick={() => {
                          setKeyInput("");
                          setState("idle");
                        }}
                        className="h-12 px-[var(--space-lg)] rounded-[var(--radius-md)] text-small font-medium text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Test Connection */}
              {settings?.has_openai_key && !isEditing && (
                <div className="mt-[var(--space-lg)] pt-[var(--space-lg)] border-t border-[var(--border-subtle)]">
                  <button
                    onClick={handleTest}
                    disabled={state === "testing"}
                    className="w-full h-12 rounded-[var(--radius-md)] bg-[var(--surface-raised)] text-small font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors disabled:opacity-50"
                  >
                    {state === "testing" ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="inline-block w-4 h-4 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
                        Testing...
                      </span>
                    ) : (
                      "Test Connection"
                    )}
                  </button>

                  {/* Status indicator */}
                  <div className="mt-[var(--space-md)] flex items-center gap-[var(--space-sm)]">
                    {testResult ? (
                      testResult.success ? (
                        <>
                          <span className="w-2 h-2 rounded-full bg-[var(--agree)]" />
                          <span className="text-mono text-[var(--agree)]">
                            Connected
                          </span>
                          <span className="text-mono text-[var(--text-ghost)]">
                            · {testResult.models_available} models available
                          </span>
                        </>
                      ) : (
                        <>
                          <span className="w-2 h-2 rounded-full bg-[var(--dismiss)]" />
                          <span className="text-mono text-[var(--dismiss)]">
                            {testResult.error || "Test failed"}
                          </span>
                        </>
                      )
                    ) : settings.openai_key_verified ? (
                      <>
                        <span className="w-2 h-2 rounded-full bg-[var(--agree)]" />
                        <span className="text-mono text-[var(--agree)]">
                          Verified
                        </span>
                        {settings.openai_key_verified_at && (
                          <span className="text-mono text-[var(--text-ghost)]">
                            · {relativeTime(settings.openai_key_verified_at)}
                          </span>
                        )}
                      </>
                    ) : (
                      <>
                        <span className="w-2 h-2 rounded-full bg-[var(--text-ghost)]" />
                        <span className="text-mono text-[var(--text-ghost)]">
                          Not tested
                        </span>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Error message */}
            {error && (
              <div className="mt-[var(--space-md)] p-[var(--space-md)] rounded-[var(--radius-md)] bg-[var(--dismiss-muted)]">
                <p className="text-mono text-[var(--dismiss)]">{error}</p>
              </div>
            )}

            {/* Footer note */}
            <p className="mt-[var(--space-lg)] text-mono text-[var(--text-ghost)]">
              Your key is encrypted and stored securely. It is only used
              for generating embeddings and AI summaries.
            </p>
          </div>
        )}
      </main>
    </>
  );
}
