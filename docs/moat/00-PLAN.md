# NewsLens — Moat Build Plan (post-handover, post-CEO-review)

> **Date:** 2026-06-24 · **Owner:** Rohit (personal project)
> **Lineage:** The `docs/enhancement/` cycle (E0–E8) shipped the table-stakes + scaffolding. The
> `NewsLens handover.zip` teardown then found the two differentiators *"announced more than
> delivered."* This plan is the **next cycle**: build the differentiation (the moat), verified.
> Sources of truth it inherits: `IMPACT_ENGINE_SPEC.md`, `PRESENTATION_FRAMEWORKS.md`, the v4
> Deep Dive mock, and `PRODUCT_CRITIQUE.md` (all in the handover package).
> **Scope decision (CEO review):** *Re-sequence around the moat.*

---

## 0. Positioning (do not drift)

NewsLens is a **personal, profession-agnostic** news-intelligence app for **anyone, in any
profession**. It is **NOT** an InvestorAi / finance product; "money" is only **one of three**
impact axes (profession · money · civic). The moat is **trust + depth-on-demand + per-persona
"what's in it for me"** — *not* auto-curation, *not* "multiple perspectives" (a funded rival,
Particle.news, already owns that), *not* summaries (commodity).

**North star:** For anyone, turn a news event into a **trustworthy personal "so what + what to
watch" in under a minute — deep on demand.**

**The wedge (where scarce effort concentrates):** per-persona decision-support **+** inspectable
reasoning. Consensus/divergence is trust-table-stakes done honestly, not the headline.

---

## 1. Sequencing principle

Trust integrity and the impact engine are the **same surface** and the **whole differentiator**,
so they ship together, first. Reasoning (Ask + frameworks) is the second half of the moat. The
habit loop comes once there's something worth returning to. The invisible depth/graph foundation
goes **last** — building it first is how this category dies (Artifact). This is the one place
first-principles overrides the handover's "graph-first" build order.

| Wave | Theme | Why this order | Effort (human → CC) |
|---|---|---|---|
| **Q** | Quick wins / hygiene | Unblocks trust + removes cruft; parallelizable | S → mins–1h |
| **A** | Trustworthy per-persona impact engine | **The wedge.** "WHAT'S IN IT FOR ME" made real + safe | L → ~half-day |
| **B** | Visible reasoning (Ask + frameworks + v4 UI) | Second half of the moat; what beats Particle | L → ~half-day |
| **C** | Habit loop (digest / alerts / follows) | Retention — only valuable once A+B exist | M → ~2–3h |
| **D** | Deepen retrieval (GraphRAG) — deferred | Invisible foundation; must not precede the moat | L → later |

Concrete engineering plan for Wave A: **[`01-wave-a-eng-plan.md`](01-wave-a-eng-plan.md)**.

---

## Wave Q — Quick wins & hygiene *(parallel, do immediately)*

| # | Item | Where | Done = |
|---|---|---|---|
| Q1 | Render the dead-wired **"why you're seeing this"** (`impact_headline` computed but never shown) | `routes.py:485` → `StoryCard.tsx` / `HeroStoryCard.tsx` | line renders on briefing cards |
| Q2 | Fix `locale` hardcoded `IN` default → user-set / geo (it's an "anyone" app) | `models.py:52`, onboarding | locale captured, not hardcoded |
| Q3 | **Keep** the trivia streak counter (owner decision; overrides handover "no streak-spam") | `DailyTriviaCard.tsx` | — (no change) |
| Q4 | Swap the **app icon** (stock Capacitor bot → NewsLens masters in the zip) | `frontend/android/.../mipmap-*`, favicon | branded icon in APK |
| Q5 | Refresh **ROADMAP.md / CLAUDE.md** (both describe the dead v2) | docs | docs match shipped reality |

---

## Wave A — The trustworthy per-persona impact engine *(THE WEDGE)*

The single highest-leverage build. The impact card is *both* the differentiator *and* where the
trust/safety risk lives — so they ship as one unit. Full engineering detail in
[`01-wave-a-eng-plan.md`](01-wave-a-eng-plan.md).

| # | Item | Atom | Where | Acceptance test |
|---|---|---|---|---|
| A1 | **Reader model to spec** — profession (free-text, any role) + interests + watchlist (entities/topics/regions) + depth_pref | A2 | `models.py`, `/profile`, onboarding | persona persists; cache key uses full persona, not profession-only |
| A2 | **Impact engine to contract** — `StoryImpact`: relevance score 0–100, per-axis `applicable / mechanism / watch_items / horizon / confidence / evidence[]`, profession·money·civic. Validated (Pydantic + structured outputs, not best-effort parse) | A3, A4 | `schemas/impact.py` (new), `lenses.py:68-80`, `llm.py:115` | 100% Pydantic-valid; **persona-sensitivity** (3 professions → meaningfully different) |
| A3 | **No-advice guardrail (all 3 layers)** — prompt rule + post-gen lint (buy/sell/hold/target-price) + UI disclaimer on the money axis | A6 | `lenses.py`, `ImpactCard.tsx:97` | **no-advice lint passes on a 50-case adversarial set**; disclaimer renders |
| A4 | **Groundedness lint** — every `evidence[].source` matches a provided source; flag numbers/entities absent from input | A6 | `lenses.py` post-gen | **0 fabricated entities** on a 30-sample audit |
| A5 | **Honesty downgrade + hype reject** — `applicable:true` w/ empty relevance → `false`; reject "game-changer/revolutionary/massive" in LLM output | A6 | `lenses.py` | thin dimensions omitted; hype tokens stripped |
| A6 | **Kill the "Sources agree" misstatement** — relabel honestly *or* compute a real concur/dissent metric (no "agreement" copy over a coherence score) | A5 | `AgreementMeter.tsx`, `ConfidenceScore.tsx` | UI no longer asserts agreement it doesn't measure |
| A7 | **Impact surface** — italic "so what" lead sentence + relevance/horizon chip + FOR YOU card backed by real A2 data | A3, A8 | `DeepDiveView.tsx`, `ImpactCard.tsx` | lead + chip render from real score |

---

## Wave B — Visible reasoning *(the second half of the moat)*

| # | Item | Atom | Where | Acceptance test |
|---|---|---|---|---|
| B1 | **"Ask this story"** — grounded, cited follow-up Q&A (keys already wired) | A7 | new `/clusters/{id}/ask`, Ask bar in `DeepDiveView.tsx` | answers cite only in-cluster sources; refuses ungrounded |
| B2 | **Frameworks as show-the-working** — 3–4 (base rate · 2nd-order · steelman · signal-vs-noise), ≤20-word line + deep-on-tap, **auto-selected by story type** (un-gate from geopolitics) | A5 | `lenses.py:83-92` → registry, `StrategicCard.tsx` | forecasts emit falsifiable condition+confidence+horizon; analogy ships disanalogy; **brevity budget enforced at generation** |
| B3 | **Consensus / Contested "where they diverge"** row — name the dissenter + the disputed point | A5 | `DeepDiveView.tsx`, backend divergence field | divergence surfaced, not just an aggregate % |
| B4 | **Brief-by-default v4 Deep Dive** — accordion (collapsed), BRIEF/FULL toggle | A8 | `DeepDiveView.tsx` rebuild to v4 | one-screen default; expand-on-tap |
| B5 | **Depth toggle** (generalist ↔ expert) | A8 | persona `depth_pref` → prompts | output depth changes with toggle |

---

## Wave C — The habit loop *(retention)*

| # | Item | Atom | Acceptance test |
|---|---|---|---|
| C1 | **AI morning digest** — "3 things that moved in your world overnight, 90-sec read" | A9 | digest generated per persona; scheduled job |
| C2 | **Breaking alerts** on high personal-relevance clusters (uses A2's score) | A9 | alert fires above threshold; not spammy |
| C3 | **Standing Follows** (entity/topic/saved-search → rail + alert) | A9, A2 | follow persists → rail + notification |

---

## Wave D — Deepen retrieval *(deferred, explicit)*

Retrieval beyond `snippet[:400]` → full-text → eventually the entity/event graph + hybrid
GraphRAG (`INTEREST_GRAPH_SPEC.md` / `KNOWLEDGE_DEPTH_ENGINE.md`, both unwritten). Deliberately
last: invisible to the user until A–C exist.

---

## Out of scope (with rationale)

- **Multi-perspective aggregation as the headline** — funded rival (Particle) owns it; we treat
  consensus/divergence as honest trust-table-stakes (B3), not the pitch.
- **Social / comments, robo-advice** — off-brand / regulatory trap (handover).
- **GraphRAG / entity-graph first** — deferred to Wave D.
- **Monetization, scale, distribution, auth/multi-user** — personal project; out of scope (auth
  already parked in `docs/enhancement/FIREBASE-DEFERRED.md`).

## Risks & flags

- **Legal (low priority, flagged):** full-text `trafilatura` extraction + substitutive AI
  summaries is the pattern in active litigation (NYT/CNN v Perplexity, Cohere). Fine for personal
  use; revisit only if distributed publicly — prefer link-out + short grounded summaries.
- **"Closed" = built AND tested:** every wave lists acceptance tests. The current suite uses a
  `fake_llm` that returns canned JSON, so it **cannot** exercise content guardrails. Wave A must
  add tests that feed adversarial content, or the guardrails are unverifiable by construction.

## Research grounding

- [Why Artifact failed (TechCrunch)](https://techcrunch.com/2024/01/18/why-artifact-from-instagrams-founders-failed-shut-down/) — "better reader + AI" is not differentiation.
- [Particle's $10.9M Series A (Nieman Lab)](https://www.niemanlab.org/reading/ai-news-reader-particle-adds-publishing-partners-and-10-9m-in-new-funding/) — multi-perspective is taken; don't compete there.
- [Reuters Institute Digital News Report 2025](https://reutersinstitute.politics.ox.ac.uk/digital-news-report/2025/dnr-executive-summary) — demand for summaries + ask-questions + visible reasoning.
- [Court: AI summaries may infringe (Copyright Lately)](https://copyrightlately.com/court-rules-ai-news-summaries-may-infringe-copyright/) — extraction legal risk.
