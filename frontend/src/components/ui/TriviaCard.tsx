"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { getClusterTrivia, type LensResult, type Difficulty } from "@/lib/api";

interface Question {
  question: string;
  options: string[];
  answer_index: number;
  explanation?: string;
}

const LEVELS: Difficulty[] = ["easy", "medium", "hard"];

/** E8 — quiz on Deep Dive. Data: GET /clusters/{id}/trivia?difficulty=.
 *  Difficulty selector; tap an option to reveal correct/incorrect + why.
 *  Hides itself when unavailable (graceful). */
export function TriviaCard({ clusterId }: { clusterId: number }) {
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [data, setData] = useState<LensResult | "loading">("loading");
  const [chosen, setChosen] = useState<Record<number, number>>({});

  useEffect(() => {
    let alive = true;
    setData("loading");
    setChosen({});
    getClusterTrivia(clusterId, difficulty)
      .then((r) => alive && setData(r))
      .catch(() => alive && setData({ unavailable: true }));
    return () => {
      alive = false;
    };
  }, [clusterId, difficulty]);

  if (data !== "loading" && data.unavailable) return null;

  const questions =
    data !== "loading" && Array.isArray(data.questions) ? (data.questions as Question[]) : [];
  if (data !== "loading" && questions.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface)] p-[var(--space-md)]"
    >
      <div className="flex items-center justify-between mb-3 gap-2">
        <span className="text-mono text-[var(--accent)]">TEST YOURSELF</span>
        <div className="flex gap-1">
          {LEVELS.map((l) => (
            <button
              key={l}
              onClick={() => setDifficulty(l)}
              className={cn(
                "text-mono text-[10px] px-2 py-0.5 rounded-full capitalize transition-colors",
                difficulty === l
                  ? "bg-[var(--accent)] text-[var(--bg)]"
                  : "bg-[var(--surface-raised)] text-[var(--text-muted)]"
              )}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {data === "loading" ? (
        <div className="skeleton h-20 w-full rounded-[var(--radius-md)]" />
      ) : (
        <div className="flex flex-col gap-4">
          {questions.map((q, qi) => {
            const pick = chosen[qi];
            const answered = pick !== undefined;
            return (
              <div key={qi}>
                <p className="text-small text-[var(--text-primary)] mb-2">
                  {qi + 1}. {q.question}
                </p>
                <div className="flex flex-col gap-1.5">
                  {q.options.map((opt, oi) => {
                    const isCorrect = oi === q.answer_index;
                    const show = answered && (oi === pick || isCorrect);
                    return (
                      <button
                        key={oi}
                        disabled={answered}
                        onClick={() => setChosen((c) => ({ ...c, [qi]: oi }))}
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
            );
          })}
        </div>
      )}

      <p className="text-mono text-[10px] text-[var(--text-ghost)] mt-3">
        AI-generated &middot; may contain errors
      </p>
    </motion.div>
  );
}
