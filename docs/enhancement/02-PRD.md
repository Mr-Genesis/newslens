# NewsLens — PRD (build spec, TDD targets)

> Source of truth for the build. Derived from [00-PLAN.md](00-PLAN.md) + [01-REVIEWS.md](01-REVIEWS.md).
> Test legend: **(U)** pure unit, native-OK · **(I)** integration, needs pgvector DB (Docker/Linux) · **(L)** LLM seam mocked.

## Vision & positioning
A **personal daily strategic-intelligence briefing sourced from news.** Every story leads with a **decision/impact verdict** — *what it means for you and what (if anything) to do* — not a summary. Works for **any profession** (doctor, PM, AI enthusiast, geopolitics geek, trader, generalist) via a **profession-agnostic engine** (free-text profession + the LLM adapts). Single-user for now (`user_id=1`); auth parked (Firebase).

## Cross-cutting requirements
- **Graceful degradation:** any LLM feature with no key returns a typed `unavailable` state, never a 500.
- **AI honesty:** every generated surface carries the "AI-generated · may contain errors" disclaimer; never show AI confidence numbers that aren't real.
- **Caching:** LLM lens outputs persist to JSONB on `story_clusters`, keyed by profession-hash, with a `source_hash`/`cache_version` so re-clustering invalidates.
- **Color budget:** monochromatic-until-interaction; AI surfaces use the violet/`drill` token; reuse existing semantic tokens (no new palette).

## Test strategy
- **Unit (U):** pure logic — explore/exploit math, free-first sort, dedup ratios, prompt builders, source upsert diff, profession-hash, JSON-repair. Run native (`pytest tests/unit`).
- **Integration (I):** anything touching SQL/pgvector/JSONB/aggregates — run against a real Postgres+pgvector via `docker-compose`; session-scoped DB + per-test transaction rollback. `pytest tests/integration` (Docker/Linux only; greenlet fails on native Win-ARM).
- **LLM seam (L):** patch `app.services.llm.generate` and `app.services.embeddings.generate_embedding`; inject deterministic strings / orthogonal unit vectors. No real API calls in tests.
- New fixtures: `db_session` (real, rollback), `seed_cluster`, `seed_articles_with_embeddings`, `fake_llm`.

---

## P-1 — E★ Foundation (hard blocker, do first)

**Story:** As a developer, I need a migratable schema and a DB-backed test harness so every later feature is TDD-able.

**Acceptance:**
- Alembic baseline migration stamps the **current** schema (9 tables) so `alembic upgrade head` on a fresh DB reproduces today's prod schema; the ad-hoc `ALTER` block in `main.py` is removed once baselined (Alembic authoritative for Neon/Render; `create_all` kept for local/test only).
- `docker-compose` test profile brings up Postgres+pgvector; `tests/integration` connects and rolls back per test.
- `app/services/llm.py` exists as the single generation seam; `tests/conftest.py` gains `fake_llm` + `db_session` fixtures.

**Test cases:**
- (I) `test_alembic_upgrade_from_empty_creates_all_tables` — upgrade head on empty DB → all 9 tables + pgvector extension present.
- (I) `test_alembic_baseline_matches_models` — `alembic revision --autogenerate` after baseline yields no diffs.
- (I) `test_integration_db_fixture_rolls_back` — row added in one test absent in the next.
- (U) `test_fake_llm_seam_returns_injected` — patched `llm.generate` returns the injected value.

---

## P0 — E0 Fixes & safety

**Story:** As a user, the multi-source intelligence I was promised is visible and the app is safe.

**Acceptance & test cases:**
1. **/feed real cluster data** — feed items carry true `source_count` + `cluster_id` from **one grouped aggregate** (count + min(cluster_id) grouped by article_id); the malformed/never-run query is replaced; no per-article N+1.
   - (I) `test_feed_item_has_real_source_count` — seed a 3-source cluster → feed item shows `source_count=3`, `cluster_id` set.
   - (I) `test_feed_no_n_plus_one` — assert query count is O(1) for an N-item page.
2. **Summary scheduler no crash** — `backfill_summaries` uses `now - timedelta(hours=4)` and applies the staleness window.
   - (U) `test_backfill_window_pre_4am_no_valueerror` — freeze time 02:00 → builds window, no error.
   - (I) `test_backfill_selects_stale_and_missing` — picks summaries that are null OR older than 4h.
3. **Reuters feed fixed** — bogus spec-page URL replaced with a working feed (or removed).
   - (U) `test_starter_feeds_urls_are_valid_feed_urls` — no URL points at `rss-specifications`/spec pages; all look like feeds.
4. **Encryption safety** — empty `ENCRYPTION_KEY` → fail-fast (no plaintext); `decrypt_value` raises on real failure instead of returning ciphertext.
   - (U) `test_encrypt_requires_key` — no key → raises, never returns plaintext.
   - (U) `test_encrypt_decrypt_roundtrip` — with key, round-trips.
   - (U) `test_decrypt_failure_does_not_leak_ciphertext`.
5. **SSL fix** — DB connect uses `verify-ca`/`verify-full` (not `CERT_NONE`).
   - (U) `test_ssl_context_not_cert_none` — built context has `verify_mode != CERT_NONE` when a CA is configured.
6. **Topic prefs persist** — Settings topic toggles write to backend `user_preferences` and affect `/briefing` & `/feed`.
   - (I) `test_put_profile_interests_persists` — PUT interests → rows in `user_preferences`.
   - (I) `test_briefing_weights_by_preferences` — preferred topic ranks higher in briefing.
7. **Frontend trust** — remove hardcoded `coh:0.85` + source-name-as-category in `DeepDiveView.tsx`; surface real cluster coherence + topic (backend returns them).
   - (I) `test_cluster_response_includes_coherence_and_topic`.
8. **Docs** — reconcile `design-system.md` (BottomTabBar, Fraunces) — doc task, no test.

---

## P1 — E1 LLM provider abstraction + Gemini

**Story:** As the owner, I wire my Gemini key so generation runs on Gemini while embeddings stay on OpenAI.

**Acceptance:**
- `services/llm.py`: `async generate(prompt, *, schema=None, model=None) -> str|dict`; provider via `settings.generation_provider` (`openai`|`gemini`); `embed()` stays bound to OpenAI in `embeddings.py`.
- Per-user Gemini key (Fernet, separate cache slot) → env `GEMINI_API_KEY` fallback.
- `schema` path uses Gemini structured output; JSON-repair (`try/except json.loads` + brace-extraction) fallback.
- `requirements.txt` += `google-generativeai`; `config.py` += `generation_provider`, `gemini_api_key`.
- `/settings` + `/settings/test-key` support Gemini key (mirrors OpenAI trio).

**Test cases:**
- (U,L) `test_generate_routes_to_provider` — provider=gemini → gemini path called; =openai → openai path.
- (U) `test_json_repair_recovers_wrapped_json` — model returns text+```json fenced``` → parsed dict.
- (U) `test_generate_no_key_returns_unavailable` — no key → typed unavailable, no exception.
- (U) `test_gemini_key_cache_slot_separate_from_openai`.
- (I) `test_put_settings_stores_gemini_key_encrypted` — key stored encrypted, never plaintext, masked last4 on GET.

---

## P1 — E6 WIIFM impact lens (the front door / hero)

**Story:** As a {profession} in {locale}, every story tells me **why it matters to me** and what to do, across Finance / Profession / Policy / Daily-life.

**Acceptance:**
- `GET /clusters/{id}/impact` → `{ headline, dimensions: [{key, label, body}], unavailable? }`, conditioned on the user's `profession`+`locale`; cached in `story_clusters.impact_json[profession_hash]` with `source_hash`.
- Feed/briefing items can carry a one-line **impact headline** (the "verdict not summary" inversion) when cheap/cached.
- Profession unset → typed "personalize" state (UI shows "Set your profession →" CTA), not generic filler.
- Disclaimer present; lazy-generated on first view, served from cache after.

**Test cases:**
- (L,I) `test_impact_generates_and_caches` — first call hits `llm.generate`; second call same (cluster,profession) does NOT (served from JSONB).
- (L,I) `test_impact_reuses_cache_per_profession_hash` — different profession → separate cache entry.
- (I) `test_impact_invalidates_on_source_hash_change` — adding an article to the cluster changes `source_hash` → regenerates.
- (U) `test_impact_unavailable_when_profession_unset`.
- (U) `test_profession_hash_stable_and_normalized` — "Doctor" / "doctor " → same hash.

---

## P1 — E3 Onboarding & personalization (all professions)

**Story:** As a new user of any profession, I pick interests fast, optionally set my profession/locale, and the feed becomes mine.

**Acceptance:**
- Data: `users.profession` (free text), `users.locale` (default `IN`); interests persisted as `user_preferences` weights (not localStorage).
- `GET/PUT /profile` (profession, locale, interests[]). Settings "Your Topics" wired to it.
- **Onboarding UX:** interests-first single screen (grid) → feed seeded immediately; **profession/locale deferred** to a dismissible Today banner ("Personalize your impact lens") that appears once impact cards exist; skippable at every step; editable in Profile; "X of 3 set up" nudge.
- Profession input = curated suggestion **chips + free-text** (serves all professions; no rigid taxonomy).

**Test cases:**
- (I) `test_put_profile_sets_profession_locale`.
- (I) `test_interests_persist_as_preferences_not_localstorage`.
- (I) `test_feed_personalizes_after_interests_set`.
- (U) `test_profession_freetext_accepted` — arbitrary string (e.g., "marine biologist") accepted.
- (frontend) `test_onboarding_skippable_each_step`; `test_profession_banner_appears_after_first_impact`.

---

## P1 — E2 Sources (India + Google News + trimmed global)

**Story:** As an India-based reader, my feed includes credible Indian + global sources.

**Acceptance:**
- Sources move to `app/data/sources.json` with `{name,url,rss_url,type,region,category,is_paywalled}`; `ensure_sources` is an **upsert** keyed on `rss_url`/`url` with an UPDATE path (backfills `region`/`category` on existing rows).
- `sources.region` = enum (`global`|`in`), nullable+default; `category` nullable.
- Feeds: fix Reuters; add AP, Guardian (global, trimmed); **India:** The Hindu, TOI, Indian Express, HT, NDTV, The Print, Scroll, LiveMint, Moneycontrol, ET Markets, Business Standard, PIB, RBI, SEBI.
- **Google News RSS** source type (per-topic query URL, `hl=en-IN&gl=IN`).
- GDELT `sourcecountry`/`sourcelang` parametrized; add `IN` query; backfill GDELT-created sources' `region`.
- Build `GET/POST /admin/sources`.

**Test cases:**
- (U) `test_sources_seed_parses_json`.
- (I) `test_ensure_sources_upsert_adds_new_without_dupes`.
- (I) `test_ensure_sources_backfills_region_on_existing`.
- (U) `test_gdelt_query_includes_country_param`.
- (U) `test_google_news_rss_url_builder` — builds correct `news.google.com/rss/search` URL.
- (I) `test_admin_post_source_creates_row`.

---

## P2 — E5 In-depth analysis tabs

**Story:** As a reader, I can go beyond the summary: Key Facts, 5Ws, and "For a {profession}".

**Acceptance:**
- `GET /clusters/{id}/analysis?lens={key_facts|5ws|profession}` → typed JSON; cached in `analysis_json[lens(/profession)]`.
- Fills the existing AISummaryBox "Coming soon" tabs + adds a 4th "For a {profession}" tab (capped at 4, scrollable <320px; unset profession → CTA).
- Lazy per-tab; disclaimer on each.

**Test cases:**
- (L,I) `test_analysis_keyfacts_returns_bullets_and_caches`.
- (L,I) `test_analysis_5ws_returns_five_keys` — who/what/when/where/why present.
- (L,I) `test_analysis_profession_lens_uses_profile`.
- (U) `test_analysis_unknown_lens_400`.

---

## P2 — E7 Strategic / game-theory lens (house voice)

**Story:** As a geopolitics geek, multi-actor stories get a strategic read — actors, incentives, the "game," and a non-obvious take; every story gets a lightweight "what's really going on" beat.

**Acceptance:**
- `GET /clusters/{id}/strategic` → `{ actors:[{name,incentive,likely_move}], game_type, second_order:[...], non_obvious_take }` via schema'd Gemini; cached.
- Auto-offered when topic ∈ world/geopolitics; collapsed-by-default disclosure UI + game-type mono Badge.
- Lightweight "what's really going on" one-liner available for any story.
- **No attribution** to specific named principles until sources validated (ship as "game-theory analysis").

**Test cases:**
- (L,I) `test_strategic_returns_structured_actors_and_game_type`.
- (L,I) `test_strategic_caches`.
- (U) `test_strategic_schema_validates_required_fields`.
- (U) `test_strategic_offered_only_for_geopolitics_topics`.

---

## P3 — E4 Hybrid search

**Story:** As any professional, I search news by keyword / interest / profession area.

**Acceptance:**
- `GET /search?q=` → **hybrid**: embed query (OpenAI, cache recent) → pgvector `<=>` NN **+** keyword `ILIKE` union → dedup by article → group by cluster → ranked.
- **HNSW index** on `articles.embedding` (migration; prerequisite).
- Frontend: activate the inert NavBar search icon → search screen; empty state with interest-seeded + recent searches; per-result "matched on: topic/meaning" mono tag.

**Test cases:**
- (I) `test_hnsw_index_exists_after_migration`.
- (L,I) `test_search_exact_keyword_ranks_above_semantic_only` — exact entity match beats paraphrase.
- (L,I) `test_search_groups_by_cluster_dedup_articles`.
- (U) `test_query_embedding_cached`.
- (I) `test_search_empty_query_400`.

---

## P3 — E8 Trivia (easy/medium/hard) + daily quiz

**Story:** As a curious reader, I test my knowledge on a story or my interest area at easy/medium/hard.

**Acceptance:**
- `GET /clusters/{id}/trivia?difficulty={easy|medium|hard}` and `GET /trivia/daily?topic=` → `[{question, options[], answer_index, explanation, difficulty}]` (schema'd Gemini); cached.
- UI: per-story collapsed disclosure (bottom of DeepDive); daily quiz as a dismissible **Today card** (not a tab); restrained mono streak counter (no confetti).

**Test cases:**
- (L,I) `test_trivia_returns_questions_for_each_difficulty`.
- (U) `test_trivia_each_question_has_answer_and_explanation`.
- (U) `test_trivia_invalid_difficulty_400`.
- (L,I) `test_trivia_caches_per_difficulty`.

---

## Data-model deltas (Alembic migrations)
- `users`: + `profession` (str, null), `locale` (str, default `'IN'`).
- `user_settings`: + `gemini_api_key_encrypted`, `gemini_key_verified` (bool), `gemini_key_verified_at`.
- `sources`: + `region` (enum global|in, null+default), `category` (str, null).
- `story_clusters`: + `analysis_json`, `impact_json`, `strategic_json`, `trivia_json` (JSONB, null) + `source_hash` (str) / `cache_version` (int).
- Index: HNSW on `articles.embedding` (E4).

## New/changed API surface
`GET/PUT /profile` · `GET /clusters/{id}/impact` · `GET /clusters/{id}/analysis` · `GET /clusters/{id}/strategic` · `GET /clusters/{id}/trivia` · `GET /trivia/daily` · `GET /search` · `GET/POST /admin/sources` · `PUT /settings` (+gemini) · `POST /settings/test-key` (+gemini).

## DeepDive IA (design-locked)
Hero (title · real coh:0.XX · src:N) → **AISummaryBox** (Summary / Key Facts / 5Ws / For a {profession}) → **Impact hero card** (headline + expandable dimension chips) → **Strategic Lens** (collapsed) → Source Spectrum → Sources (free-first) → **Trivia** (collapsed, bottom). Lazy-generate on reveal; disclaimer on all AI surfaces.
