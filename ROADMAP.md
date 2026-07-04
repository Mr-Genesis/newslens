# Roadmap — NewsLens

> **Active plan:** the post-handover differentiation work lives in [`docs/moat/00-PLAN.md`](docs/moat/00-PLAN.md)
> (Waves Q–D) with the Wave A engineering spec in [`docs/moat/01-wave-a-eng-plan.md`](docs/moat/01-wave-a-eng-plan.md).
> This file tracks the older MVP→v2 backlog.

## Current Status

**Working:**
- Data pipeline: RSS + GDELT fetching, dedup, embedding, clustering, **entity extraction** (G1, gated) — all on APScheduler
- API: ~40 endpoints (feed, briefing, discover, cluster lenses, **entities + appears-in**, **follows + digest**, ask/frameworks/consensus/timeline, profile, settings, search, admin, stats, auth)
- Frontend: Briefing, Discover, Deep Dive, Search, Saved, Settings, Onboarding, **entity cast strip**
- Real LLM features shipped (E1–E8): provider abstraction (**OpenAI + Anthropic + Gemini**, Wave E BYOM), real AI summaries,
  analysis/5Ws/profession lenses, **per-persona Impact engine v2 (structured + guarded, Wave A)**,
  strategic lens, trivia/daily quiz
- **Knowledge graph (Wave D Phase 3):** G1 global entity backbone (entities/aliases/article links + cast strip) and G2 per-user entity-relevance overlay; **personalized ranking across cast strip + feed + briefing + search, ON by default (`UER_ENABLED`)** — zero-signal users are a no-op
- **Source expansion (Phases 1–3, PR #77/#84/#91):** persona-gated **research + expert** source tiers with credibility scoring, tier badges, credibility-weighted feed rank, follow-a-source opt-in, admin + monthly-LLM credibility review, and weekly **PubMed / arXiv** personal research feeds — 117-source union (45 gated). See **Source Expansion** section below.
- **Auth (Wave D Phase A):** Firebase (Google + Email/Password), `get_current_user` + Postgres RLS on per-user tables; `AUTH_REQUIRED=false` keeps single-user dev
- Feedback-driven explore/exploit (0.3 is now only a cold-start fallback; swipes move weights)
- Design system: Full spec + CSS token implementation
- Mobile: Capacitor Android APK builds
- Brand: authentic NewsLens launcher icon (adaptive) + native splash (mark + Fraunces wordmark on #0C0C0E) + web/PWA favicons, all from the official brand kit; `@capacitor/splash-screen` controlled splash → WebView fade
- Per-user **OpenAI + Anthropic + Gemini** API key + model management with Fernet encryption

**Still stubbed / heuristic:**
- Cluster `coherence` now prefers the **real source-agreement ratio** (agree/total from a cached
  consensus pass) and only falls back to the source-overlap heuristic (0.95/0.85/0.75/0.65) when no
  consensus is cached — the UI labels it honestly ("Source overlap")
- Tension lines on discover cards still fall back to article titles when no AI line exists

**🔜 Deferred / still open (post-G2 hardening — tracked, not blocking):**
- ⏸️ **Impressions retention** (from the 2026-07-04 Follow-Anything plan review): the `impressions`
  table (WS-1 of that wave) is capped ~500 rows/user/day but unbounded over time (~15k rows/user/month).
  Add a monthly prune job — delete rows >180 days, optionally keeping per-(user,surface,month) aggregate
  counts for long-horizon CTR. Not needed until the table actually matters; wiring mirrors the existing
  monthly credibility-review cron.
- ⏸️ **Render paid-tier revisit trigger** (decision 2026-07-04, re-opens itself): chose free tier +
  keepalive. **Trigger to upgrade the WEB service to Starter ($7/mo): two pipeline stalls in one week OR
  the first real second user.** Rationale on file: a separate background worker was REJECTED — Render has
  no free worker tier (same $7), and splitting jobs out of the web process breaks the in-process SSE
  events hub (`events.py`) without a Postgres LISTEN/NOTIFY bridge; Starter-web gets always-on scheduler +
  no user cold-starts with zero code changes.
- ⏸️ **§2b — `_source_hash` widening** — deliberately deferred until a lens becomes entity/user-dependent.
  No lens reads graph/user data yet, so widening now would only add per-user lens-cache cost. Widen the
  hash to include entity ids + content version + user scope the moment a personalized/graph-reading lens
  starts caching. Breadcrumb lives in `backend/app/services/entities.py` + `docs/moat/04,07,09`.
- 🔜 **Still open:** the deferred **G3 graph work** (embedding-NN entity resolution / reversible
  auto-merge, multi-hop recursive-CTE lenses — correctly gated behind real-user volume + a co-typed-homonym
  precision fixture, see `docs/moat/09`), the two unbuilt endpoints (**`GET /events`** SSE §1.3,
  **`GET /admin/breadth`** §2.2), the **`/feed?source_type=…` filter-chip UI** (#82 — the API filter +
  `getFeed(sourceType)` shipped; the chip UI waits on a rendered feed screen), the **PubMed `source_hash`
  cache-widening** (§2b, tracked above), discover **"tension lines"** §3.1, and **native push** (Wave C2
  on-device half). The plan's **PubMed RSS GUID path was rejected** (403 from NCBI) — PubMed ingest uses
  E-utilities esearch/efetch instead.

---

## Phase 1: Core AI (High Priority)

These fill the biggest MVP gaps — the app functions but lacks its AI intelligence core.

### 1.1 AI Summaries
Replace hardcoded coherence scores and stub summaries with real GPT-4o-mini calls in `/briefing` and `/discover/deck`. Config already exists in `backend/app/config.py` (`summary_model`, `summary_batch_size`).

### 1.2 Dynamic Explore/Exploit Ratio
Implement feedback-driven adjustment of the explore ratio. Currently hardcoded at 0.3 in config. Should analyze recent feedback (window of 50) to shift between 0.1-0.5. Infrastructure exists in `user_preferences.weight` and `user_preferences.breadth_score`.

### 1.3 SSE Events Endpoint
Implement `GET /events` for real-time feed updates. Events: `new_article`, `new_cluster`, `feed_refresh`. Library `sse-starlette` is already in requirements. Frontend would subscribe on mount for live updates.

---

## Phase 2: Production Readiness (Medium Priority)

### 2.1 Deploy Backend Publicly
Required for the APK to work on real devices (currently points to `10.0.2.2:8000` which only works in emulator). Options: Fly.io, Render, or Railway. Docker setup already exists.

### 2.2 Admin Endpoints
`GET`/`POST /admin/sources` shipped (list + upsert; upsert requires a `credibility_score` for research/expert tiers, 0–100), plus `PUT /admin/sources/{id}/credibility` (#85 — admin applies a score + rationale, stamps `reviewed_by="admin"` to lock the row against the seed re-upsert). Still open: `GET /admin/breadth` (evaluation metrics: topic coverage, source diversity).

### 2.3 Test Coverage Gaps
Current tests cover API layer + encryption + settings. Missing:
- `test_fetcher.py` — RSS parsing, error handling
- `test_gdelt.py` — GDELT API integration
- `test_dedup.py` — URL match + fuzzy title dedup
- `test_clustering.py` — pgvector distance thresholds
- `test_briefing.py` — Briefing endpoint with real clusters
- `test_discover.py` — Discover deck generation + swipe recording

### 2.4 Run Skillchain Domains
76 skills across 10 domains installed in `~/.claude/commands/skillchain/`. Run security, frontend, backend, devops, infrastructure, developer, data, ai-ml skillchains for comprehensive project analysis. Requires fresh Claude Code session (commands loaded at startup).

---

## Phase 3: Polish (Lower Priority)

### 3.1 AI Tension Lines
Generate compelling "tension line" for discover cards using GPT — the core conflict of a story in one sentence. Currently falls back to article title.

### 3.2 Topic Auto-Assignment
Automatically categorize articles into topics using embedding similarity. Currently topics exist in the schema but aren't auto-populated.

### 3.3 Pull-to-Refresh
Implement in briefing screen. Full spec exists in `design-system.md` (threshold: 60px, rubber-band resistance curve, accent spinner).

### 3.4 Orientation Handling
Landscape card sizing per design-system.md: `min(360px, 60vh)` card height, percentage-based swipe thresholds.

### 3.5 Custom App Icon ✅ Shipped
The default Capacitor robot is gone — adaptive launcher icon, native splash, and web/PWA favicons are regenerated from the official NewsLens brand kit. See [Brand & App Identity](design-system.md#brand--app-identity).

---

## Source Expansion (Phases 1–3) ✅ Shipped

Adds persona-gated **research** + **expert** source tiers on top of the news feed: high-credibility sources are shown only to a matching profession or an explicit follower, with credibility scoring, badges, ranking, and personal research feeds.

### Phase 1 — Tiers + persona gating (PR #77)
- `SourceType` gains **research** / **expert**; migration `b2c3d4e5f6a7` adds 6 nullable `sources` columns: `author_name`, `credibility_score` (0–100), `credibility_meta` (JSONB), `audience` (text[]), `is_preprint`, `per_fetch_cap`.
- `services/audience.py`: `tags_for_profession()` → tags; `allowed_source_ids(tags, floor, followed)` → subquery. A gated source is shown only above a credibility floor **and** with a matching audience (feed floor **55**, briefing floor **70** — `credibility_feed_floor` / `credibility_briefing_floor`).
- `fetcher._upsert_sources` admin-lock: a `credibility_meta.reviewed_by == "admin"` row survives the 10-min seed re-upsert; `per_fetch_cap` enforced; `_best_body` takes the longer of summary vs `content:encoded`.
- `POST /admin/sources` requires `credibility_score` for research/expert (400) and validates 0–100. `sources.json` is a **117-source union (45 gated)**; `SourceOut` exposes `author_name` / `credibility_score` / `is_preprint`.

### Phase 2 — Badges + ranking + follow-source (PR #84)
- Frontend `SourceTierBadge` (RESEARCH / EXPERT + author + score; PREPRINT + "not peer-reviewed") on StoryCard / SourceCard / DiscoverCard; `BriefingStory` gains a `tier` field (#78).
- Feed-rank credibility multiplier ×`(0.9 + 0.2·score/100)`, bounded `[0.9, 1.1]`; NULL (news) → neutral **75** (`credibility_rank_neutral`), clamped 0–100 (#79).
- Briefing **+0.15** `story_weights` bonus for a persona-matched gated cluster (`credibility_briefing_bonus`) (#80).
- Follow-a-source opt-in: `follows.kind = "source"` (zero migration); `allowed_source_ids` gains an OR-followed branch that bypasses **both** the floor and the audience match; frontend `FollowButton` "source" kind on SourceCard (#81).
- `GET /feed?source_type=news|research|expert` filter (invalid → 400); `getFeed(sourceType)` in the API client (#82). **The filter-chip UI is deferred** — no rendered feed screen yet.
- Discover deck reserves up to **5** gated cards (`discover_gated_slots`) + a follow affordance; `DiscoverCardOut` gains `source_id` / `source_type` / `is_gated` / `is_preprint` / `author_name` / `credibility_score` (#83).

### Phase 3 — Credibility ops + personal research feeds (PR #91, backend-only, no new migration)
- `PUT /admin/sources/{id}/credibility` — admin applies a score + rationale, stamps `reviewed_by="admin"`; 400 out-of-range, 404 unknown (#85).
- `services/credibility.py` `review_credibility()` — **monthly** cron, **propose-only**: writes `credibility_meta.proposed_score` + `reviewed_by="llm-proposed"` for gated rows unreviewed >90d (`credibility_review_stale_days`); never touches the live score, preserves the admin lock, no-ops without a platform LLM key (#90).
- `services/pubmed.py` — NCBI E-utilities adapter (esearch JSON, efetch XML) + `ingest_pubmed()` **weekly** cron: maps a medical profession → search term, ingests recent abstracts as gated research articles (`audience=["medicine"]`), ≤3 req/s throttle, optional `ncbi_api_key`, deduped by PMID (`pubmed_enabled` / `pubmed_min_request_interval` 0.34 / `pubmed_retmax` 25) (#86).
- `services/arxiv_gen.py` — maps subscribed-topic interests → arXiv categories (cs.CV, cs.RO, q-bio, …) and idempotently ensures those research sources; **weekly** cron (#87).
- `audience.resolve_tags()` — keyword map fast path + LLM classifier fallback constrained to the fixed tag vocabulary, cached per user on `persona_version`; wired into the feed + briefing gates; no key → keyword-only (#88).
- `entities._extraction_candidates()` — research-tier clusters extract at **1** source (`graph_extract_research_min_sources`); news keeps the min-2 "settled" bar (#89).
- Three new APScheduler cron jobs in `main.py`: `credibility_review` (monthly, 1st @ 03:00), `pubmed_ingest` (weekly Mon 04:00), `arxiv_generate` (weekly Mon 04:30).

---

## Known Limitations

| Issue | Workaround | Root Cause |
|-------|------------|------------|
| Turbopack doesn't work | `--webpack` flag in all npm scripts | Windows ARM not supported |
| Backend can't run natively on Windows ARM | Run in Docker | greenlet DLL load failure breaks SQLAlchemy async |
| Android emulator doesn't work | Use physical device or skip | QEMU2 + WOW64 incompatibility on ARM |
| Dynamic routes fail in Capacitor build | Dual routing: `[clusterId]` (web) + `?id=X` (Capacitor) | Next.js static export can't handle dynamic segments |
| JDK 17 insufficient for Capacitor | JDK 21 required | Capacitor Android Gradle config targets Java 21 |
| `@capacitor/assets` / `sharp` can't generate icons | Deterministic `System.Drawing` resize from the brand kit | sharp won't load on Windows ARM; current `@capacitor/assets` emits broken adaptive output |
