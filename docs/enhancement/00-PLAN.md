# NewsLens — Enhancement Plan (v1)

> Status: REVIEWED. **Authoritative final scope, phasing & decisions live in [01-REVIEWS.md](01-REVIEWS.md)** (post CEO/Eng/Design review + owner reconciliation). This file is the original draft; where it conflicts with 01-REVIEWS.md, the latter wins. The build spec is [02-PRD.md](02-PRD.md).
> Date: 2026-06-23. Owner: Rohit (personal project).
>
> **Key post-review changes:** added **P-1 Foundation** (Alembic baseline + pgvector integration-test DB + LLM mock seam) as the first hard-blocker phase; **WIIFM impact (E6) promoted to the P1 front door**; strategic lens (E7) = "house voice" in P2; **all-professions kept** via a profession-agnostic engine (free-text profession, no heavy taxonomy); **trivia (E8) + search (E4) kept** but moved to P3; SSL `CERT_NONE` fix + design-system.md reconcile added to P0.

## 0. Positioning (corrected)

NewsLens is a **personal, profession-agnostic news-intelligence app**. It is **not** an InvestorAi product and must not be coupled to it. The thesis: *"Breadth, not bubbles"* — multi-source clustering + AI analysis that adapts to **whoever you are**.

Every persona is first-class:

| Persona | Core job | Signature value |
|---|---|---|
| Doctor / clinician | Track developments in their field | "What changed in cardiology this week + why it matters to practice" |
| Product manager | Track product/tech/market moves | "What this launch means for product strategy" |
| AI enthusiast | Track AI research & industry | "What's new, who shipped, what's hype" |
| Geopolitics geek | Track world events | **Game-theory strategic lens** (see §5.7) — each party's incentives, the "game" being played, non-obvious takes |
| Investor / market trader | Track market-moving news | "How this may impact markets / sectors" |
| Generalist | Stay informed, fast | Personalized briefing + "why this matters to me" |

The unifying engine: a **"What's in it for me" (WIIFM) layer** keyed on each user's **profession + interests + locale**, applied to every story.

## 1. Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Database / infra | **Stay on Neon + Render** for the build; "evaluate Supabase" parked | Auth is Firebase (not Supabase Auth), so Supabase's main draw is moot; don't migrate infra + add features simultaneously. Supabase MCP is connected → easy future move if Neon SSL/cold-starts persist. |
| Auth & Sign-in | **Firebase Auth (incl. Google sign-in)** — **SCOPED & PARKED** (see [FIREBASE-DEFERRED.md](FIREBASE-DEFERRED.md)) | Multi-user is a large lift; do features first. App stays single-user (`user_id=1`) until then. |
| Push notifications | **Firebase Cloud Messaging** — **PARKED** with auth | Ties to the existing notification-engine thinking; needs auth first. |
| LLM — generation | **Gemini** (`gemini-2.0-flash` / `1.5-flash`) via a provider abstraction | Cheap, strong for summaries/analysis/trivia; user has keys. |
| LLM — embeddings | **Keep OpenAI `text-embedding-3-small` (1536-dim)** for now | Switching to Gemini (768-dim) forces a pgvector column change + full re-embed; decouple that migration from feature work. |
| Google item #1 (Gemini) | Build now | — |
| Google item #2 (Sign-in) | = Firebase Auth → parked | — |
| Google item #3 (Google News) | Build now as a source | Cheap breadth + recency. |

## 2. Build-now scope (epics)

- **E0 — P0 fixes** (make the existing brain visible & safe)
- **E1 — LLM provider abstraction + Gemini** (generation)
- **E2 — Sources: India + global + Google News + admin/upsert + GDELT country**
- **E3 — Onboarding: interests + profession + locale; persist; personalize feed**
- **E4 — Semantic search** (by keyword / interest / profession)
- **E5 — In-depth analysis** (Key Facts, 5Ws, "Explain for a {profession}")
- **E6 — WIIFM impact lens** (multi-dimension, profession-aware)
- **E7 — Strategic / game-theory lens** (geopolitics)
- **E8 — Trivia** (easy / medium / hard) + daily quiz loop

## 3. Parked (scoped, not built now)

- **Firebase Auth** (Google sign-in, multi-user) — [FIREBASE-DEFERRED.md](FIREBASE-DEFERRED.md)
- **Firebase Cloud Messaging** (push) — depends on auth
- **Gemini embeddings migration** (768-dim re-embed) — optional later
- **Supabase migration** — optional later
- SSE live updates, vernacular/multi-language, admin breadth dashboard

## 4. Non-goals (this phase)

- No paid/multi-tenant accounts beyond the single-user model.
- No real-money or InvestorAi integration.
- No mobile-native rewrite (Capacitor wrapper stays).

## 5. Detailed scoping (per epic)

### E0 — P0 fixes
- **/feed cluster bug**: the cluster-count query is built but never executed; `source_count` hardcoded to 1, `cluster_id` always None (`routes.py:110-131`). Fix so feed items carry real `source_count` + `cluster_id` (multi-source visible).
- **Summary crash**: `backfill_summaries` does `hour-4` → ValueError before 4am (`summarizer.py:149`). Use a safe windowed query.
- **Reuters feed**: replace the bogus URL (points at RSS spec page, `fetcher.py:124`) with a working feed; remove if none.
- **Encryption safety**: empty `ENCRYPTION_KEY` silently stores plaintext (`encryption.py:22`). Fail-fast or generate+persist a key; never store plaintext.
- **Wire topic chips**: Settings topic toggles are localStorage-only & inert (`settings/page.tsx:108`). Persist to backend `user_preferences` and make them affect the feed.
- (Frontend trust) remove hardcoded coherence `0.85` & source-name-as-category in `DeepDiveView.tsx`; surface real cluster coherence + topic.

### E1 — LLM provider abstraction + Gemini
- New `backend/app/services/llm.py`: `async generate(prompt, *, json=False, model=None)` and `async embed(text)`; provider switch via `settings.llm_provider` (`openai` | `gemini`).
- `config.py`: add `LLM_PROVIDER`, `GEMINI_API_KEY`; `requirements.txt`: add `google-generativeai`.
- Per-user Gemini key: add `gemini_api_key_encrypted` to `user_settings` (mirror OpenAI), reuse Fernet (`encryption.py`).
- Refactor `summarizer.generate_cluster_summary` and the new analysis features to call `llm.generate`. Embeddings stay on OpenAI (`embeddings.py`) for now.
- Graceful degradation preserved: no key → snippet fallback.

### E2 — Sources
- Move `STARTER_FEEDS` to `backend/app/data/sources.json` (or config); `ensure_sources` becomes an **upsert** (adds new feeds to existing DBs), not "only when empty" (`fetcher.py:140`).
- Add global feeds (fix Reuters; add AP, Guardian, CNBC, Politico, Axios) + **India** feeds (The Hindu, TOI, Indian Express, HT, NDTV, The Print, Scroll, LiveMint, Moneycontrol, ET Markets, Business Standard, PIB, RBI, SEBI). Tag each with `region` (`global`/`in`) and optional `category`.
- **Google News RSS** as a source type: `https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en` — enables per-topic ingestion.
- **GDELT**: parametrize `sourcecountry`/`sourcelang` (`gdelt.py:38`) → add an `IN` query alongside `US`.
- Build the unused **`POST /admin/sources`** + `GET /admin/sources` endpoints (schemas already exist).

### E3 — Onboarding + personalization
- First-run flow (frontend): pick **interests** (topics), **profession/role** (from a curated list + free text), **locale** (default India). Skippable.
- Data model: add `profession` (string) + `locale` (string) to `users` (or a `user_profile` table); persist selected interests as `user_preferences` rows (real topic weights), not localStorage.
- New endpoints: `GET/PUT /profile` (profession, locale, interests). Wire Settings "Your Topics" to it.
- Personalize: `/briefing` + `/feed` weight by stored preferences (the explore/exploit logic already exists server-side; feed it real weights).

### E4 — Semantic search
- `GET /search?q=...` → embed query (OpenAI) → pgvector nearest-neighbor over `articles.embedding` + keyword `ILIKE` fallback; group by cluster; rank.
- Frontend: activate the dead navbar search icon → search screen with results list (reuse StoryCard). Recent/suggested searches by interest.

### E5 — In-depth analysis (Gemini)
- Replace the "Coming soon" tabs (`AISummaryBox.tsx:90,126`): **Key Facts** (bulleted extraction), **5Ws** (who/what/when/where/why), and new **"For a {profession}"** lens.
- Backend: `GET /clusters/{id}/analysis?lens={key_facts|5ws|profession}` → Gemini over the cluster's source texts; cache on `story_clusters` (new JSON columns) to avoid recompute.

### E6 — WIIFM impact lens (Gemini)
- Per cluster, generate **"How this affects you"** across dimensions the user cares about: **Finance / markets, Profession, Policy & regulation, Daily life** — conditioned on `profession` + `locale`.
- Backend: `GET /clusters/{id}/impact` (uses profile); cache per (cluster, profession) hash. Frontend: an "Impact" card on Deep Dive.
- Profession-agnostic: doctor → clinical-practice impact; trader → market impact; PM → product/strategy impact, etc.

### E7 — Strategic / game-theory lens (Gemini)
- For **geopolitics / multi-actor** stories: a **"Strategic Lens"** that, inspired by **Prof. Jiang Xueqin's game-theory commentary**, analyzes: (a) the actors/parties, (b) each party's incentives & likely payoffs, (c) the type of "game" (zero-sum, coordination, chicken, prisoner's dilemma, signalling), (d) second-order effects & a **non-obvious take**.
- Backend: `GET /clusters/{id}/strategic`; Gemini with a structured prompt + schema. Auto-offered when topic ∈ geopolitics/world.
- ⚠️ **Source-fidelity note:** the specific "Jiang Xueqin principles" must be sourced/validated (link real essays) before claiming attribution; until then frame as "game-theory strategic analysis." (Confidence: needs validation.)

### E8 — Trivia (easy/medium/hard)
- Gemini generates quiz questions from a story or a topic, three difficulty tiers, each with the correct answer + a one-line explanation.
- `GET /clusters/{id}/trivia?difficulty=` and `GET /trivia/daily?topic=` (by interest). Frontend: "Test your knowledge" on a story + a **daily quiz** with streaks (engagement loop; future FCM hook).

## 6. Data-model deltas (summary)

- `users`: + `profession`, `locale` (or new `user_profile`).
- `user_settings`: + `gemini_api_key_encrypted`, `gemini_key_verified`.
- `sources`: + `region`, `category` (+ JSON seed file).
- `story_clusters`: + `analysis_json`, `impact_json`, `strategic_json`, `trivia_json` (caches).
- All via Alembic migrations.

## 7. Phasing

| Phase | Epics | Goal |
|---|---|---|
| P0 | E0 | Existing brain visible + safe |
| P1 | E2, E3, E4 | Relevance: India sources, personalization, search → "this is mine" |
| P2 | E1, E5, E6 | Gemini value: deep analysis + WIIFM impact |
| P3 | E7, E8 | Differentiators: strategic lens + trivia/engagement loop |

(E1 is foundational and may land at the start of P2 or earlier since E5–E8 depend on it.)

## 8. Risks

- **Gemini cost/latency** on per-cluster analysis → cache aggressively (§6 JSON columns), generate lazily on view.
- **Embedding-dim trap** if Gemini embeddings are adopted later (768 vs 1536) → separate migration.
- **Profession taxonomy** sprawl → curated list + free-text fallback; map free text → nearest curated for prompting.
- **Game-theory attribution** (Jiang Xueqin) → validate sources before attributing.
- **Single-user model** limits real personalization testing until Firebase auth lands.

## 9. Open questions (for reviews)

1. Profession taxonomy: curated list size? (10 broad vs 50 granular)
2. Analysis caching: per-cluster (shared) vs per-(cluster,profession) (personalized) — cost vs relevance.
3. Trivia: per-story vs daily-by-topic as the primary loop?
4. Search: semantic-only vs hybrid (keyword+semantic) for v1?
