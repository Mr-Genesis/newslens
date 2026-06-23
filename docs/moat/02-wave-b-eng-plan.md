# Wave B — Engineering Plan: Visible Reasoning (Ask · Frameworks · v4 UI)

> Parent: [`00-PLAN.md`](00-PLAN.md). Builds on Wave A ([`01-wave-a-eng-plan.md`](01-wave-a-eng-plan.md)).
> Goal: the second half of the moat — let the reader **interrogate** a story (Ask) and **see the
> reasoning** (frameworks + consensus/divergence), inside the brief-by-default v4 Deep Dive.
> Reviewed: CEO (scope set by 00-PLAN), Eng, Design (findings inline below).

## Scope
- **B1 Ask this story** — grounded, cited follow-up Q&A.
- **B2 Frameworks** — the ~8-lens library (base rate · 2nd-order · steelman · signal-vs-noise · incentives · precedent+disanalogy · bayesian-update · reflexivity, + game-theory geopolitics-gated), one-line + deep-on-tap, auto-selected by story type, **≤4 chips surfaced** (un-gate the strategic-only lens).
- **B3 Consensus / Contested** — the real "where they diverge" metric (replaces the Wave-A honest-but-flat "Source overlap").
- **B4 Brief-by-default v4 Deep Dive** — collapsed accordion + BRIEF/FULL.
- **B5 Depth toggle** — generalist ↔ expert (consumes Wave A's `depth_pref`).

## What already exists (reuse, don't rebuild)
- `llm.generate` seam (+ `max_tokens`, provider routing) — reuse for Ask + frameworks.
- The Wave A cache pattern (`_cache_read`/`_cache_write` JSONB-merge + TTL, `get_lens`) — reuse for frameworks (`strategic_json` → generalize to `frameworks_json`).
- `StrategicCard` + `lenses._prompt_strategic` — **generalize** into the framework registry (don't add a parallel system).
- `depth_pref` column + persona (Wave A) — B5 just switches the prompt.
- `impact_guardrails` token-matching + groundedness helpers — reuse for the framework "groundable / no-advice" guardrail.

## Contracts
**B1 Ask** — `POST /clusters/{id}/ask` `{question}` → `{answer, citations:[{claim, source}], refused?:bool}`.
Grounded to the cluster's sources only; refuses (not hallucinates) when the answer isn't in-cluster.
Not cached per-question (cost bounded by `max_tokens` + a short answer budget); rate-limited per cluster.

**B2 Frameworks** — a registry (mirrors the handover's `PRESENTATION_FRAMEWORKS` schema):
```
{ id, label, question, auto_fire:[story_types], render_template, deep_structure, guardrail, word_budget }
```
`GET /clusters/{id}/frameworks` → `{ frameworks: [{id, label, one_liner, deep?}] }`, auto-selected by the
cluster's topic/story-type, capped at 4 chips. Each one-liner ≤20 words (enforced in prompt + a length lint).
Forecast/analogy frameworks must emit a falsifiable condition / disanalogy (guardrail).

## Eng review findings (applied)
- **E1 Reuse, don't fork:** generalize `strategic_json` → `frameworks_json` keyed by `framework_id`; the strategic lens becomes one registry entry (game_theory) rather than a separate endpoint. Avoids a parallel cache/codepath (DRY).
- **E2 Ask cost/abuse:** Ask is uncached + LLM-per-call → bound it: `max_tokens` cap, max question length, and a simple per-cluster call ceiling; on provider failure return typed `unavailable` (never 500), same pattern as Wave A.
- **E3 Ask grounding:** reuse the groundedness lint — answer citations must map to in-cluster outlets; if the model can't ground, return `refused:true` with a "not in these sources" message (no fabrication).
- **E4 Frameworks brevity:** the ≤20-word budget is enforced at generation AND a post-gen length lint truncates/regenerates — not CSS-only (the "enforced, not hoped" principle).
- **E5 Tests (the bar): ** unit — registry auto-selection by story type, ≤20-word lint, falsifiability/disanalogy presence; integration — Ask grounded/refusal paths (adversarial fake_llm returning an ungrounded answer → refused), frameworks cache + cap-at-4. Extend the `fake_llm` with ask/frameworks branches.

## Design review findings (applied)
- **D1 v4 accordion (B4):** collapsed-by-default rows (SUMMARY / FOR YOU / CONSENSUS / FRAMEWORKS / SOURCES) + BRIEF/FULL toggle; the Wave A lead sentence + relevance chip stay above the fold. Reuse design-system motion + tokens; reduced-motion guard on expand.
- **D2 Interaction states:** Ask — idle (prompt), thinking (skeleton), answered (cited), refused ("not in these sources"), error (retry). Frameworks — loading chips, empty (no framework fired → row hidden), one-liner→deep on tap.
- **D3 Consensus (B3):** the "WHERE THEY DIVERGE" callout names the dissenting outlet + the disputed point; honest when n is small. This is the real metric that retires the Wave-A relabel.
- **D4 a11y:** Ask input labelled; framework chips are buttons (keyboard-operable, 44px); answer region `aria-live="polite"`; non-color state cues.

## Decisions (resolved 2026-06-24)
1. **Frameworks v1 = the ~8 library:** base rate · 2nd-order · steelman · signal-vs-noise · incentives · precedent+disanalogy · bayesian-update · reflexivity (+ game-theory, geopolitics-gated). Each ≤20-word render, deep-on-tap, auto-selected by story type, **cap 4 chips on the surface** (rest behind "more lenses"). More prompts/guardrails/tests — budget accordingly.
2. **Ask = uncached + bounded** (max_tokens + question-length + per-cluster ceiling). No question-hash cache in v1.
3. **Consensus (B3) = a single grounded LLM pass** over the cluster sources extracting the agree/dissent split + the disputed point (fits the lens+cache pattern). No separate stance-detection pipeline in v1.

## NOT in scope
- Standing follows / digest / alerts (Wave C). Entity-impact (later). GraphRAG retrieval depth (Wave D).
- Per-framework "tracked falsifiable call" history (a Wave D+ analytics feature).

## Checklist (ordered)
- [ ] Generalize cache column `strategic_json` → `frameworks_json`; registry module + auto-selection
- [ ] `GET /clusters/{id}/frameworks` (cap 4, ≤20-word lint, falsifiability/disanalogy guardrail)
- [ ] `POST /clusters/{id}/ask` (grounded, cited, refusal, bounded) + Ask bar UI
- [ ] B3 consensus/divergence field + "WHERE THEY DIVERGE" UI row
- [ ] B4 v4 accordion + BRIEF/FULL toggle (rebuild DeepDiveView layout)
- [ ] B5 depth toggle → prompt switch (uses `depth_pref`)
- [ ] Tests: unit (registry, brevity, guardrail) + integration (ask grounded/refused, frameworks cap) + frontend (accordion, Ask states); extend fake_llm
- [ ] Validate: Docker pytest + `npm run build` + vitest + lint:copy
