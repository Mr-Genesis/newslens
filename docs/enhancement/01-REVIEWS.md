# NewsLens Plan — CEO / Eng / Design Reviews + Decisions

> Three independent reviews of [00-PLAN.md](00-PLAN.md), then synthesis, then owner reconciliation.
> Date: 2026-06-23. Method: parallel critic agents (workflow `wf_4012c66b-811`).

## Review highlights

**CEO / founder** — *Right direction, wrong center of gravity.* WIIFM impact + the game-theory/second-order lens is the only non-commodity idea and it's buried in P2/P3. Reframe from "news reader that explains" → **"a daily strategic-intelligence briefing sourced from news"** where every story carries a **decision/impact verdict, not a summary**. Make the strategic lens the **house voice**. (Also urged: collapse personas, defer search, cut trivia — see Reconciliation below.)

**Eng / architecture** — Technically sound, but **two hard blockers**: (1) `migrations/versions/` is **empty** — schema is `create_all` + ad-hoc `ALTER`; no Alembic baseline → no new SQL is migratable. (2) Tests are **100% mocked** (`MockSession` sniffs SQL strings) → pgvector/JSONB/aggregate features are untestable. Must add a **migration baseline + pgvector integration-test DB + LLM mock seam FIRST**. Plus: split `generation_provider` from embeddings (keep embed on OpenAI), `generate(prompt, *, schema=None)` with JSON-repair, **HNSW index** before search, `/feed` as one aggregate (the current query is malformed + N+1), **SSL `CERT_NONE` is a real MITM hole** (missed by plan), JSONB caches keyed by profession-hash, integration tests run in **Docker/Linux only** (greenlet/Win-ARM).

**Design** — Features are strong but the plan adds **7+ blocks to DeepDive with no IA** → AI scroll-wall that buries the source-first/confidence-first soul. Lock the DeepDive IA: **one AI hub** (tabs in the existing AISummaryBox) + **Impact as the hero card** + **Strategic/Trivia collapsed disclosures**. Onboarding **interests-first** (profession/locale deferred to a Today banner that arrives *with* the payoff). Every generated surface needs the **AI disclaimer**; keep **monochromatic-until-interaction** (AI = violet/drill token). Reconcile the **stale design-system.md** (says top-nav + Instrument Serif; app ships BottomTabBar + Fraunces).

## Decision log (condensed from synthesis)

**Adopted in full:** Foundation phase first (Alembic baseline + pgvector test DB + LLM seam); E1 LLM abstraction locked to front of P1; **WIIFM impact promoted to P1 hero / front door**; strategic lens = house voice (P2), generalize the "what's really going on" beat to all stories; DeepDive IA (one AI hub + Impact hero + collapsed Strategic/Trivia); onboarding interests-first + profession-unset graceful CTAs; reframe positioning to "decision/impact verdict not summary."

**Eng specifics adopted:** `profession`/`locale` → **`users` columns**; Gemini key mirrors full OpenAI trio (`gemini_api_key_encrypted`, `gemini_key_verified`, `gemini_key_verified_at`); `sources.region` **enum** (`global`/`in`) nullable+default, upsert on `rss_url`/`url` with UPDATE path; cluster caches **JSONB** keyed by profession-hash + **cache-version/source-hash** for invalidation; `generation_provider` separate, `embed()` stays OpenAI, second key-cache slot for Gemini; `generate(prompt, *, schema=None)` + JSON-repair; **HNSW index** prerequisite of search; **hybrid search**; `/feed` single aggregate; summary fix `now - timedelta(hours=4)` + apply window; encryption fail-fast + tighten `decrypt_value`; **SSL verify-ca/full**; backfill GDELT source region; lazy one-lens-per-endpoint; integration tests in Docker.

**Design specifics adopted:** AISummaryBox capped at 4 scrollable tabs; Impact = headline + expandable dimension chips, distinct accent; Strategic collapsed w/ teaser + game-type mono Badge; search empty-state (interest-seeded + recent) + "matched on" tag; disclaimer on all generated surfaces; reconcile design-system.md (P0 doc task).

## Reconciliation with owner's explicit requirements (overrides)

The CEO review is advisory; the owner gave explicit product requirements that take precedence. Three deliberate divergences from the synthesis:

| Synthesis said | Owner requirement | Final decision |
|---|---|---|
| Collapse to 1 persona; defer taxonomy | "NewsLens for **all professions**, not just mine" (doctor, PM, AI enthusiast, geopolitics geek, trader…) | **Keep multi-profession** — but implement as a **profession-agnostic engine**: free-text `profession` + curated suggestion chips (NOT a 50-item ontology). The lenses take the profession string and adapt via the LLM, so it serves *any* profession with zero taxonomy. Satisfies both "all professions" and "ship the lens not the ontology." |
| Cut trivia until auth | Owner explicitly wants **trivia easy/medium/hard** | **Keep trivia** — sequence at **P3** (after the wedge), restrained tone (mono streak, no confetti), daily quiz as a Today card not a tab. |
| Defer search | Owner wants **search by interest/profession** | **Keep search** at **P3**, hybrid + HNSW (synthesis already kept it thin — aligned). |

## Finalized phasing (reconciled)

| Phase | Epics | Goal |
|---|---|---|
| **P-1 Foundation** | **E★** Alembic baseline · pgvector integration-test DB · LLM/embeddings mock seam | Make the codebase TDD-able (hard blocker) |
| **P0 Fix & safe** | **E0** + SSL `CERT_NONE` fix + design-system.md reconcile | Existing brain visible, safe, trustworthy |
| **P1 Wedge** | **E1** LLM abstraction → **E6** WIIFM impact (hero/front door) → **E3** onboarding (interests-first + free-text profession, all professions) → **E2** sources (India + Google News + trimmed global) | Lead with "what this means for me" |
| **P2 Depth** | **E5** analysis tabs → **E7** strategic/game-theory lens (house voice) | Differentiated point-of-view |
| **P3 Utility & engagement** | **E4** hybrid search (+HNSW) → **E8** trivia (easy/med/hard) + daily quiz | Owner-requested; after the wedge |
| **Parked** | Firebase Auth, FCM, Gemini-embeddings migration, Supabase | Post-auth / future |

## Resolved open questions

1. **Profession taxonomy:** free-text + curated suggestion chips on `users` (no heavy ontology) — serves all professions.
2. **Analysis caching:** per-(cluster, profession-hash), stored `{profession:{...}}` in JSONB; cache-version/source-hash invalidation.
3. **Trivia loop:** kept (owner) — daily-by-topic as primary, Today card; per-story as collapsed disclosure.
4. **Search:** hybrid (semantic-primary + keyword union, dedup by article, group by cluster) + HNSW index.
