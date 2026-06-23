"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { getDailyTrivia, type LensResult } from "@/lib/api";

interface Question {
  question: string;
  options: string[];
  answer_index: number;
  explanation?: string;
}

/** Per-day dismissal key so the card returns each new day. */
function todayKey(): string {
  return `newslens-daily-quiz-${new Date().toISOString().slice(0, 10)}`;
}

/** E8 — daily quiz as a dismissible Today card (not a tab).
 *  Data: GET /trivia/daily. Tap an option to reveal correct/incorrect + why.
 *  Hides itself when unavailable, empty, or already dismissed today. */
export function DailyTriviaCard() {
  const [data, setData] = useState<LensResult | "loading">("loading");
  const [pick, setPick] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (localStorage.getItem(todayKey())) return; // already dismissed today
    setDismissed(false);
    let alive = true;
    getDailyTrivia()
      .then((r) => alive && setData(r))
      .catch(() => alive && setData({ unavailable: true }));
    return () => {
      alive = false;
    };
  }, []);

  function dismiss() {
    if (typeof window !== "undefined") localStorage.setItem(todayKey(), "1");
    setDismissed(true);
  }

  if (dismissed) return null;
  if (data !== "loading" && data.unavailable) return null;

  const questions =
    data !== "loading" && Array.isArray(data.questions) ? (data.questions as Question[]) : [];
  if (data !== "loading" && questions.length === 0) return null;

  // Daily quiz is a single bite-sized question.
  const q = questions[0];
  const answered = pick !== null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: 0.3 }}
        className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface)] p-[var(--space-md)] mb-4"
      >
        <div className="flex items-center justify-between mb-3 gap-2">
          <span className="text-mono text-[var(--accent)]">DAILY QUIZ</span>
          <button
            onClick={dismiss}
            aria-label="Dismiss daily quiz"
            className="text-mono text-[var(--text-ghost)] hover:text-[var(--text-muted)] transition-colors text-[10px]"
          >
            DISMISS &times;
          </button>
        </div>

        {data === "loading" || !q ? (
          <div className="skeleton h-20 w-full rounded-[var(--radius-md)]" />
        ) : (
          <div>
            <p className="text-small text-[var(--text-primary)] mb-2">{q.question}</p>
            <div className="flex flex-col gap-1.5">
              {q.options.map((opt, oi) => {
                const isCorrect = oi === q.answer_index;
                const show = answered && (oi === pick || isCorrect);
                return (
                  <button
                    key={oi}
                    disabled={answered}
                    onClick={() => setPick(oi)}
                    className={cn(
                      "text-left text-small px-3 py-2 rounded-[var(--radius-md)] border transition-colors",
                      !answered &&
                        "border-[var(--border-subtle)] bg-[var(--surface-raised)] text-[var(--text-secondary)] hover:border-[var(--text-muted)]",
                      show && isCorrect &&
                        "border-[var(--agree)] bg-[var(--agree-muted)] text-[var(--agree)]",
                      show && !isCorrect &&
                        "border-[var(--dismiss)] bg-[var(--dismiss-muted)] text-[var(--dismiss)]",
                      answered && !show &&
                        "border-[var(--border-subtle)] text-[var(--text-ghost)]"
                    )}
                  >
                    {opt}
                  </button>
                );
              })}
            </div>
            {answered && q.explanation && (
              <p className="text-mono text-[var(--text-muted)] mt-2">{q.explanation}</p>
            )}
          </div>
        )}

        <p className="text-mono text-[10px] text-[var(--text-ghost)] mt-3">
          AI-generated &middot; may contain errors
        </p>
      </motion.div>
    </AnimatePresence>
  );
}
