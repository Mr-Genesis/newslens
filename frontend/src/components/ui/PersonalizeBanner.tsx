"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { getProfile, updateProfile } from "@/lib/api";

/** Set once the user has encountered an impact card that needs a profession
 *  (ImpactCard's profession_unset state). The banner only appears after that. */
export const IMPACT_SEEN_KEY = "newslens-impact-seen";
const DISMISSED_KEY = "newslens-personalize-dismissed";

const PROFESSION_CHIPS = [
  "Investor", "Founder", "Engineer", "Doctor", "Student", "Policymaker", "Journalist",
];
const LOCALES = ["IN", "US", "GB", "global"];

/** E3 — "Personalize your impact lens" Today banner. Profession/locale are
 *  deferred off onboarding to here, and this only shows AFTER the user has met
 *  their first impact card (IMPACT_SEEN_KEY). Dismissible; profession is also
 *  editable later from Profile. Curated chips + free-text. */
export function PersonalizeBanner() {
  // "idle" until we've decided; null once we know it should not render.
  const [state, setState] = useState<"idle" | "show" | "hidden">("idle");
  const [profession, setProfession] = useState("");
  const [locale, setLocale] = useState("IN");
  const [interestsSet, setInterestsSet] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // Gates: must have met an impact card, not already dismissed.
    if (!localStorage.getItem(IMPACT_SEEN_KEY) || localStorage.getItem(DISMISSED_KEY)) {
      setState("hidden");
      return;
    }
    let alive = true;
    getProfile()
      .then((p) => {
        if (!alive) return;
        setLocale(p.locale || "IN");
        setInterestsSet(Boolean(p.interests && p.interests.length > 0));
        // Only nudge when profession is still unset — that's the missing piece.
        setState(p.profession && p.profession.trim() ? "hidden" : "show");
      })
      .catch(() => alive && setState("hidden"));
    return () => {
      alive = false;
    };
  }, []);

  function dismiss() {
    if (typeof window !== "undefined") localStorage.setItem(DISMISSED_KEY, "1");
    setState("hidden");
  }

  async function save() {
    if (!profession.trim()) return;
    setSaving(true);
    try {
      await updateProfile({ profession: profession.trim(), locale });
    } catch {
      /* proceed — editable later in Profile */
    } finally {
      if (typeof window !== "undefined") localStorage.setItem(DISMISSED_KEY, "1");
      setState("hidden");
    }
  }

  if (state !== "show") return null;

  // "X of 3 set up": locale (has a default) + interests + profession-in-progress.
  const setupCount = 1 + (interestsSet ? 1 : 0) + (profession.trim() ? 1 : 0);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: 0.3 }}
        className="rounded-[var(--radius-lg)] border border-[var(--accent-muted)] bg-[var(--accent-subtle)] p-[var(--space-md)] mb-4"
      >
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="text-mono text-[var(--accent)]">PERSONALIZE YOUR IMPACT LENS</span>
          <button
            onClick={dismiss}
            aria-label="Dismiss personalization"
            className="text-mono text-[10px] text-[var(--text-ghost)] hover:text-[var(--text-muted)] transition-colors"
          >
            NOT NOW &times;
          </button>
        </div>
        <p className="text-mono text-[10px] text-[var(--text-muted)] mb-3">
          {setupCount} of 3 set up &middot; add your profession so every story leads with what it means for you.
        </p>

        <div className="flex flex-wrap gap-2 mb-2">
          {PROFESSION_CHIPS.map((c) => (
            <button
              key={c}
              onClick={() => setProfession(c)}
              className={cn(
                "px-3 py-1.5 rounded-full text-small transition-colors",
                profession === c
                  ? "bg-[var(--accent)] text-[var(--bg)]"
                  : "bg-[var(--surface-raised)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              )}
            >
              {c}
            </button>
          ))}
        </div>
        <Input
          value={profession}
          onChange={(e) => setProfession(e.target.value)}
          placeholder="or type your field — e.g. Trader, Teacher"
          aria-label="Your profession"
        />

        <div className="flex gap-2 mt-3">
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

        <Button
          variant="primary"
          size="sm"
          onClick={save}
          loading={saving}
          disabled={!profession.trim()}
          className="mt-3"
        >
          Personalize
        </Button>
      </motion.div>
    </AnimatePresence>
  );
}
