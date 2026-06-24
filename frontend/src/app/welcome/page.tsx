"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

/**
 * Welcome — first-run intro carousel (official "Splash & Onboarding" design,
 * Direction B). Three value-prop pages, then "Get started" hands off to the E3
 * topic picker at /onboarding. Returning users (already onboarded) are bounced
 * straight to the app.
 */
const ONBOARDED_KEY = "newslens-onboarded";

function Kicker({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-mono uppercase tracking-[0.18em] text-[var(--text-muted)] mb-3.5">
      {children}
    </p>
  );
}

function Headline({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <h1
      className={cn(
        "italic font-semibold leading-[0.98] tracking-[-0.02em] text-[var(--text-primary)] text-[40px] sm:text-[44px] font-[family-name:var(--font-fraunces)]",
        className
      )}
    >
      {children}
    </h1>
  );
}

function Body({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[15px] leading-relaxed text-[var(--text-secondary)] mt-4">
      {children}
    </p>
  );
}

function Slide({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex-[0_0_33.3333%] h-full flex flex-col px-7 pt-[72px] pb-[112px]", className)}>
      {children}
    </div>
  );
}

export default function WelcomePage() {
  const router = useRouter();
  const [page, setPage] = useState(0);

  // Returning users skip the intro.
  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem(ONBOARDED_KEY)) {
      router.replace("/");
    }
  }, [router]);

  const next = () => setPage((p) => Math.min(2, p + 1));
  const back = () => setPage((p) => Math.max(0, p - 1));
  const toPicker = () => router.push("/onboarding");

  return (
    <div className="relative mt-[calc(var(--page-top)*-1)] mb-[calc(var(--page-bottom)*-1)] min-h-[100dvh] bg-[#0C0C0E] flex flex-col overflow-hidden">
      {/* Top controls */}
      <div className="h-12 flex items-center justify-between px-4 pt-[var(--safe-top)] shrink-0 z-10">
        {page > 0 ? (
          <button onClick={back} className="text-mono uppercase tracking-[0.1em] text-[var(--text-muted)]">
            &larr; Back
          </button>
        ) : (
          <span />
        )}
        {page < 2 ? (
          <button onClick={toPicker} className="text-mono uppercase tracking-[0.1em] text-[var(--text-muted)]">
            Skip
          </button>
        ) : (
          <span />
        )}
      </div>

      {/* Track */}
      <div className="flex-1 relative overflow-hidden">
        <div
          className="flex h-full w-[300%] transition-transform duration-500 [transition-timing-function:cubic-bezier(0.5,0.05,0.18,1)]"
          style={{ transform: `translateX(-${(page * 100) / 3}%)` }}
        >
          {/* Page 1 — spotlight */}
          <Slide className="!pt-[64px]">
            <div className="flex-1 flex items-center justify-center">
              {/* Framed spotlight — the mark in a viewfinder ring with outer source ticks (official brand spotlight) */}
              <svg viewBox="0 0 100 100" width={210} height={210} className="overflow-visible" role="img" aria-hidden>
                <g stroke="var(--border)" strokeWidth={3} strokeLinecap="round">
                  <line x1="6" y1="22" x2="17" y2="22" />
                  <line x1="2" y1="50" x2="14" y2="50" />
                  <line x1="6" y1="78" x2="17" y2="78" />
                  <line x1="83" y1="22" x2="94" y2="22" />
                  <line x1="86" y1="50" x2="98" y2="50" />
                  <line x1="83" y1="78" x2="94" y2="78" />
                </g>
                <circle cx="50" cy="50" r="26" fill="none" stroke="var(--border-subtle)" strokeWidth={1} />
                <path d="M35 26 H22 V74 H35" fill="none" stroke="var(--text-primary)" strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
                <path d="M65 26 H78 V74 H65" fill="none" stroke="var(--text-primary)" strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="50" cy="50" r="7.5" fill="var(--accent)" />
              </svg>
            </div>
            <Kicker>News intelligence</Kicker>
            <Headline>
              Ten headlines.
              <br />
              <span className="text-[var(--accent)]">One</span> story.
            </Headline>
            <Body>
              Every outlet on a story, bracketed down to what actually happened. One
              clear story — not fifty tabs.
            </Body>
          </Slide>

          {/* Page 2 — spectrum */}
          <Slide>
            <div className="flex-1 flex flex-col justify-center">
              <div className="italic font-semibold leading-none text-[60px] text-[var(--text-primary)] font-[family-name:var(--font-fraunces)]">
                88<span className="text-[30px] text-[var(--text-muted)]">%</span>
              </div>
              <p className="text-mono uppercase tracking-[0.12em] text-[var(--text-muted)] mt-2 mb-7">
                Outlets agree on the facts
              </p>
              <div
                className="relative h-4 rounded-full"
                style={{ background: "linear-gradient(90deg,#27272A,#3F3F46,#27272A)" }}
              >
                <div className="absolute top-[-6px] bottom-[-6px] w-[2px] bg-[var(--accent)]" style={{ left: "62%" }} />
                <div
                  className="absolute top-[-13px] w-[9px] h-[9px] rounded-full bg-[var(--accent)]"
                  style={{ left: "62%", transform: "translateX(-50%)" }}
                />
              </div>
              <div className="flex justify-between text-mono uppercase tracking-[0.1em] text-[var(--text-muted)] mt-2.5">
                <span>Left</span>
                <span>Center</span>
                <span>Right</span>
              </div>
            </div>
            <Kicker>See every side</Kicker>
            <Headline>
              Read across
              <br />
              the spectrum.
            </Headline>
            <Body>
              See where left, center and right converge — and exactly where they split.
            </Body>
          </Slide>

          {/* Page 3 — make it yours */}
          <Slide className="!pb-10">
            <div className="flex-1 flex items-center justify-center relative min-h-[150px]">
              <div
                className="absolute w-[150px] h-[92px] border border-[var(--border-subtle)] rounded-[10px] bg-[#0C0C0E]"
                style={{ transform: "translate(18px,-20px)" }}
              />
              <div
                className="absolute w-[150px] h-[92px] border border-[var(--border)] rounded-[10px] bg-[#0C0C0E] p-3.5"
                style={{ transform: "translate(-14px,14px)" }}
              >
                <div className="flex items-center gap-2 mb-2.5">
                  <span className="w-2 h-2 rounded-full bg-[var(--accent)]" />
                  <span className="text-mono uppercase tracking-[0.1em] text-[var(--text-muted)]">Following</span>
                  <span className="ml-auto text-[var(--text-primary)] text-[13px]">&#9733;</span>
                </div>
                <div className="h-2 w-[90%] bg-[var(--text-ghost)] rounded mb-1.5" />
                <div className="h-[7px] w-[60%] bg-[var(--surface-raised)] rounded" />
              </div>
            </div>
            <Kicker>Make it yours</Kicker>
            <Headline className="!text-[34px] mb-5">
              Your brief,
              <br />
              every morning.
            </Headline>
            <button
              onClick={toPicker}
              className="w-full h-12 rounded-[10px] bg-[var(--text-primary)] text-[#0C0C0E] font-medium text-[14.5px]"
            >
              Get started
            </button>
            <p className="text-center text-[12.5px] text-[var(--text-muted)] mt-4">
              Pick your topics next — it takes ten seconds.
            </p>
          </Slide>
        </div>
      </div>

      {/* Bottom: dots + next */}
      <div className="h-24 flex items-center justify-between px-6 pb-[var(--safe-bottom)] shrink-0 z-10">
        <div className="flex gap-[7px] items-center">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className={cn(
                "h-1.5 rounded-full transition-all duration-300",
                i === page ? "w-5 bg-[var(--text-primary)]" : "w-1.5 bg-[var(--text-ghost)]"
              )}
            />
          ))}
        </div>
        {page < 2 && (
          <button
            onClick={next}
            className="h-[46px] px-6 rounded-full bg-[var(--text-primary)] text-[#0C0C0E] font-medium text-[14.5px] flex items-center gap-2"
          >
            Next &rarr;
          </button>
        )}
      </div>
    </div>
  );
}
