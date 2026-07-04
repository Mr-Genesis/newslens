"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { getProfile, updateProfile } from "@/lib/api";

const LOCALES = ["IN", "US", "GB", "global"];

/** v2 Profile additions: Profession + Locale (drives the impact lens) + Depth. Self-contained.
 *  (WS-6: the Gemini key moved into the unified ModelProviderCard.) */
export function ProfileFields() {
  const [profession, setProfession] = useState("");
  const [locale, setLocale] = useState("IN");
  const [depth, setDepth] = useState("standard"); // B5: generalist ↔ expert
  const [loaded, setLoaded] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);

  useEffect(() => {
    getProfile()
      .then((p) => {
        setProfession(p.profession ?? "");
        setLocale(p.locale ?? "IN");
        setDepth(p.depth_pref ?? "standard");
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  async function saveProfile() {
    setSavingProfile(true);
    setProfileSaved(false);
    try {
      await updateProfile({ profession: profession.trim() || null, locale, depth_pref: depth });
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 2000);
    } catch {
      /* ignore */
    } finally {
      setSavingProfile(false);
    }
  }

  return (
      <Card variant="raised">
        <div className="p-3.5">
          <h2 className="text-category text-[var(--text-muted)] mb-3">PROFILE</h2>

          <label className="text-small text-[var(--text-secondary)] block mb-1">
            Profession
          </label>
          <Input
            value={profession}
            onChange={(e) => setProfession(e.target.value)}
            placeholder="e.g. Product Engineer, Doctor, Trader"
            disabled={!loaded}
          />
          <p className="text-mono text-[var(--text-ghost)] mt-2">
            Tailors the &ldquo;What&apos;s in it for me&rdquo; impact lens to you.
          </p>

          <label className="text-small text-[var(--text-secondary)] block mt-4 mb-1">
            Locale
          </label>
          <div className="flex gap-2">
            {LOCALES.map((l) => (
              <button
                key={l}
                onClick={() => setLocale(l)}
                className={cn(
                  "px-3 py-1.5 rounded-[var(--radius-md)] text-mono transition-colors",
                  locale === l
                    ? "bg-[var(--accent)] text-[var(--bg)]"
                    : "bg-[var(--surface-raised)] text-[var(--text-muted)]"
                )}
              >
                {l}
              </button>
            ))}
          </div>

          <label className="text-small text-[var(--text-secondary)] block mt-4 mb-1">
            Depth
          </label>
          <div className="flex gap-2">
            {(["brief", "standard", "expert"] as const).map((d) => (
              <button
                key={d}
                onClick={() => setDepth(d)}
                className={cn(
                  "px-3 py-1.5 rounded-[var(--radius-md)] text-mono capitalize transition-colors",
                  depth === d
                    ? "bg-[var(--accent)] text-[var(--bg)]"
                    : "bg-[var(--surface-raised)] text-[var(--text-muted)]"
                )}
              >
                {d}
              </button>
            ))}
          </div>
          <p className="text-mono text-[var(--text-ghost)] mt-2">
            How deep the AI goes — generalist to expert.
          </p>

          <Button
            variant="primary"
            size="sm"
            onClick={saveProfile}
            loading={savingProfile}
            className="mt-4"
          >
            {profileSaved ? "Saved" : "Save profile"}
          </Button>
        </div>
      </Card>
  );
}
