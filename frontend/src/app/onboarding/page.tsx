"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { getProfile, updateProfile } from "@/lib/api";

const TOPICS = [
  "AI", "Markets", "World", "Technology", "Science", "Health",
  "Politics", "Business", "Sports", "Climate", "Geopolitics",
];

const ONBOARDED_KEY = "newslens-onboarded";

export default function OnboardingPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [interests, setInterests] = useState<string[]>([]);
  const [profession, setProfession] = useState("");
  const [saving, setSaving] = useState(false);

  // Returning users (profile already set) skip onboarding.
  useEffect(() => {
    let alive = true;
    getProfile()
      .then((p) => {
        if (!alive) return;
        if (p.profession || (p.interests && p.interests.length > 0)) {
          localStorage.setItem(ONBOARDED_KEY, "1");
          router.replace("/");
        } else {
          setReady(true);
        }
      })
      .catch(() => alive && setReady(true));
    return () => {
      alive = false;
    };
  }, [router]);

  function toggle(topic: string) {
    setInterests((cur) =>
      cur.includes(topic) ? cur.filter((t) => t !== topic) : [...cur, topic]
    );
  }

  async function finish() {
    setSaving(true);
    try {
      await updateProfile({
        profession: profession.trim() || null,
        interests,
      });
    } catch {
      /* proceed regardless — they can edit in Profile */
    } finally {
      localStorage.setItem(ONBOARDED_KEY, "1");
      router.replace("/");
    }
  }

  if (!ready) {
    return (
      <div className="mx-auto max-w-[640px] w-full px-[var(--space-lg)] pt-[var(--space-2xl)]">
        <div className="skeleton h-8 w-48 rounded mb-4" />
        <div className="skeleton h-40 w-full rounded" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto max-w-[640px] w-full px-[var(--space-lg)] pt-[var(--space-2xl)] pb-[var(--space-2xl)]"
    >
      <p className="text-mono text-[var(--accent)] mb-2">WELCOME TO NEWSLENS</p>
      <h1 className="text-hero text-[var(--text-primary)]">
        What do you want to follow?
      </h1>
      <p className="text-small text-[var(--text-muted)] mt-2">
        Pick a few topics — your briefing adapts as you read.
      </p>

      <div className="flex flex-wrap gap-2 mt-[var(--space-lg)]">
        {TOPICS.map((t) => {
          const on = interests.includes(t);
          return (
            <button
              key={t}
              onClick={() => toggle(t)}
              className={cn(
                "px-3.5 py-2 rounded-full text-small transition-colors",
                on
                  ? "bg-[var(--accent)] text-[var(--bg)]"
                  : "bg-[var(--surface-raised)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              )}
            >
              {t}
            </button>
          );
        })}
      </div>

      <div className="mt-[var(--space-xl)]">
        <label className="text-small text-[var(--text-secondary)] block mb-1">
          What&apos;s your field? <span className="text-[var(--text-ghost)]">(optional)</span>
        </label>
        <Input
          value={profession}
          onChange={(e) => setProfession(e.target.value)}
          placeholder="e.g. Product Engineer, Doctor, Trader"
        />
        <p className="text-mono text-[var(--text-ghost)] mt-2">
          Powers the &ldquo;What&apos;s in it for me&rdquo; lens on each story.
        </p>
      </div>

      <div className="mt-[var(--space-xl)] flex items-center gap-3">
        <Button variant="primary" onClick={finish} loading={saving} disabled={interests.length === 0}>
          Start reading
        </Button>
        <Button variant="ghost" onClick={finish} disabled={saving}>
          Skip
        </Button>
      </div>
    </motion.div>
  );
}
