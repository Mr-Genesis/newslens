# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Backend (Python FastAPI)
cd backend && pip install -r requirements.txt   # Install backend deps
cd backend && uvicorn app.main:app --reload     # Start backend dev server (port 8000)
cd backend && pytest                            # Run backend tests
cd backend && alembic upgrade head              # Run database migrations (fresh DB → applies baseline f76aec9da324)
cd backend && alembic stamp head                # Existing DB built by init_db: mark it at baseline without re-creating
cd backend && alembic revision --autogenerate -m "description"  # Create new migration
# Note: alembic env runs via the sync driver (psycopg2). On native Windows-ARM use Docker;
# autogenerate against an EMPTY DB so it emits CREATE TABLEs (set DATABASE_URL_SYNC + PYTHONPATH=/app).

# Frontend (Next.js)
cd frontend && npm install                      # Install frontend deps
cd frontend && npm run dev                      # Start frontend dev server (port 3000)
cd frontend && npm run build                    # Production build (uses --webpack flag)
cd frontend && npx vitest                       # Run frontend tests
cd frontend && npx playwright test              # Run E2E tests

# Docker
docker-compose up                               # Start all services (DB + backend)
docker-compose down                             # Stop all services
docker-compose up db                            # Start only PostgreSQL

# Linting
cd backend && ruff check .                      # Python linting
cd frontend && npm run lint                     # TypeScript/Next.js linting

# Mobile / Android (Capacitor)
cd frontend && npm run build:android            # Static export + Capacitor sync
cd frontend && npm run apk:debug               # Build debug APK via Gradle
# APK output: frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

## Architecture

NewsLens is an AI-powered news intelligence platform. Two-language stack: Python backend (data pipeline + ML) and TypeScript frontend (UI). They communicate via REST JSON — no shared types needed. Mobile builds use Capacitor to wrap the Next.js static export into a native Android WebView app.

**Stack:** Next.js 16 App Router, React 19, Tailwind CSS 4, Framer Motion, Python FastAPI, PostgreSQL + pgvector, multi-provider LLM (Gemini embeddings + Gemini/OpenAI/Anthropic generation), Firebase Admin SDK (auth), APScheduler, Capacitor (Android) + `@capacitor/splash-screen`

**Key architectural decisions:**
- pgvector nearest-neighbor SQL for clustering (not Python pairwise — O(n) vs O(n²))
- APScheduler (AsyncIOScheduler) inside FastAPI process for cron jobs
- Next.js `rewrites` in `next.config.ts` proxying `/api/*` → `localhost:8000` (no CORS needed in web mode)
- `rapidfuzz` for title dedup (10-100x faster than python-Levenshtein)
- `asyncpg` (not psycopg2) to preserve FastAPI's async benefits
- Multi-user via Firebase Auth + Postgres RLS: `get_current_user` verifies the ID token and sets the GUC `app.user_id`; per-user tables (`user_feedback`, `user_preferences`, `user_settings`, `follows`, `user_entity_relevance`) are RLS-scoped. `AUTH_REQUIRED=false` keeps the single-user dev fallback (`user_id` FK still everywhere)
- Multi-provider LLM generation (BYOM): Gemini / OpenAI / Anthropic, per-user encrypted key + model selection (`active_provider` + `model_prefs` JSONB), env-var platform fallback for background jobs; embeddings on Gemini (`gemini-embedding-001`, 768-dim)
- Knowledge graph: a global entity backbone (G1) + a per-user entity-relevance overlay (G2) personalize ranking across the cast strip, feed, briefing, and search (gated by `UER_ENABLED`, on by default; zero-signal users are a no-op)
- Per-user API keys Fernet-encrypted in `user_settings` (+ env fallback)
- Capacitor static export with conditional `next.config.ts` (`BUILD_TARGET=capacitor`)
- Capacitor static export with conditional `next.config.ts` (`BUILD_TARGET=capacitor`)
- Dual story routes: `/story/[clusterId]` (web dynamic) + `/story?id=X` (Capacitor static export)
- Brand assets (adaptive launcher icon, native splash, favicons) regenerate from one official brand kit via deterministic `System.Drawing` resize — `@capacitor/assets`/`sharp` are broken on Windows ARM (see Windows ARM Notes)
- `@capacitor/splash-screen` holds the native splash (`launchAutoHide: false`) and cross-fades into the in-app splash on native

## Directory Structure

```
news-app/
├── backend/                           # Python FastAPI backend
│   ├── app/
│   │   ├── main.py                   # FastAPI app, lifespan, scheduler setup
│   │   ├── config.py                 # Pydantic settings (env vars)
│   │   ├── database.py               # SQLAlchemy async engine + session
│   │   ├── models.py                 # SQLAlchemy ORM models (16 tables) + RLS DDL events
│   │   │                             #   incl. entities, entity_aliases, article_entities (G1),
│   │   │                             #   user_entity_relevance (G2), follows (C), cluster_edges (D2)
│   │   ├── schemas.py                # Pydantic request/response schemas
│   │   ├── api/
│   │   │   └── routes.py             # All REST endpoints
│   │   └── services/
│   │       ├── fetcher.py            # RSS feed fetcher (feedparser + httpx)
│   │       ├── gdelt.py              # GDELT API integration (URL discovery + trafilatura)
│   │       ├── dedup.py              # Deduplication (URL match + rapidfuzz title similarity)
│   │       ├── embeddings.py         # Gemini embedding generation + backfill (gemini-embedding-001)
│   │       ├── clustering.py         # pgvector nearest-neighbor story clustering
│   │       ├── encryption.py         # Fernet encryption for per-user API keys
│   │       ├── llm.py                # Multi-provider LLM generation (OpenAI/Anthropic/Gemini)
│   │       ├── auth.py               # Firebase ID-token verify + get_current_user (sets GUC app.user_id)
│   │       ├── entities.py           # G1/G2 entity backbone: extraction, resolution, relevance scorer
│   │       ├── audience.py           # Source-expansion gate: profession→tags, allowed_source_ids subquery
│   │       ├── credibility.py        # Monthly propose-only LLM credibility review (writes proposed_score)
│   │       ├── pubmed.py             # NCBI E-utilities adapter + weekly PubMed research ingestion
│   │       └── arxiv_gen.py          # Weekly arXiv-by-interest research source generation
│   ├── tests/
│   │   ├── conftest.py               # Pytest fixtures + test DB setup
│   │   ├── test_api.py               # API endpoint tests
│   │   ├── test_encryption.py        # Encryption/decryption tests
│   │   └── test_settings.py          # Settings API tests
│   ├── migrations/                    # Alembic database migrations
│   ├── requirements.txt               # Python dependencies
│   └── Dockerfile
├── frontend/                          # Next.js 16 frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx              # Home / Briefing screen
│   │   │   ├── layout.tsx            # Root layout with NavBar
│   │   │   ├── globals.css           # Design system token implementation
│   │   │   ├── discover/
│   │   │   │   └── page.tsx          # Swipe deck discover screen
│   │   │   ├── settings/
│   │   │   │   └── page.tsx          # API keys + provider selection (OpenAI/Anthropic/Gemini)
│   │   │   └── story/
│   │   │       ├── [clusterId]/
│   │   │       │   ├── page.tsx      # Deep dive (web — dynamic route)
│   │   │       │   └── loading.tsx   # Route loading skeleton (StoryLoadingSkeleton)
│   │   │       ├── page.tsx          # Deep dive (Capacitor — query param)
│   │   │       └── StoryContent.tsx  # Client component for query-param routing
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   └── NavBar.tsx        # Top navigation with 3-segment bar
│   │   │   ├── DeepDiveView.tsx      # Multi-source cluster detail panel
│   │   │   ├── DiscoverCard.tsx      # Swipe card for discover deck
│   │   │   ├── SourceCard.tsx        # Individual source article card
│   │   │   ├── StoryCard.tsx         # Briefing story card with summary
│   │   │   └── ui/
│   │   │       ├── AISummaryBox.tsx  # AI-generated summary display
│   │   │       ├── Badge.tsx         # Topic/category badge
│   │   │       ├── ConfidenceScore.tsx # src:N · coh:0.XX display
│   │   │       ├── SourceTierBadge.tsx # RESEARCH / EXPERT (+author +score) / PREPRINT tier badge
│   │   │       └── Skeleton.tsx      # Skeletons: StoryCard / DeepDive / StoryLoading
│   │   └── lib/
│   │       ├── api.ts                # API client (env-aware base URL)
│   │       └── utils.ts              # cn() utility (clsx + tailwind-merge)
│   ├── android/                       # Capacitor Android project
│   ├── capacitor.config.ts            # Capacitor config (appId: com.newslens.app)
│   ├── next.config.ts                 # Conditional: rewrites (web) or static export (Capacitor)
│   └── package.json
├── docker-compose.yml                 # PostgreSQL + pgvector + backend
├── design-system.md                   # Visual design spec (colors, typography, spacing)
├── ARCHITECTURE.md                    # System architecture + diagrams
├── ROADMAP.md                         # Feature roadmap + known limitations
├── CONTRIBUTING.md                    # Developer onboarding guide
└── .env.example                       # Environment variable template
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | /health | Health check (DB status) |
| GET | /feed | Paginated feed with explore/exploit mix |
| GET | /feed?topic={id} | Topic-filtered feed |
| GET | /feed?source_type={news\|research\|expert} | Source-tier-filtered feed (invalid → 400; chip UI deferred) |
| GET | /clusters/{id} | Story cluster with all source articles (free first) |
| GET | /topics | All topics grouped: your_topics, explore, trending |
| POST | /feedback | Record user feedback (interesting/less/save/share) |
| GET | /briefing | Daily AI briefing (top 8 clusters with article fallback) |
| GET | /discover/deck | 20-30 randomized discovery swipe cards |
| POST | /discover/swipe | Record swipe action + adjust topic weights |
| GET | /discover/topic/{id} | 5 topic-specific cards |
| GET | /settings | User settings (masked API key) |
| PUT | /settings | Save/remove OpenAI API key (Fernet encrypted) |
| POST | /settings/test-key | Validate OpenAI API key |
| GET | /saved | User's saved articles list |
| DELETE | /saved/{article_id} | Remove a saved article |
| GET | /stats | Reading stats (articles read, saved, topics explored) |
| GET/PUT | /profile | Persona: profession, locale, interests, watchlist, depth_pref, region |
| PUT | /settings/gemini-key | Save/remove per-user Gemini key (Fernet) |
| POST | /settings/test-gemini-key | Validate Gemini key |
| PUT | /settings/anthropic-key | Save/remove per-user Anthropic key (Fernet) |
| POST | /settings/test-anthropic-key | Validate Anthropic key |
| GET | /clusters/{id}/analysis | Key Facts / 5Ws / profession lens |
| GET | /clusters/{id}/impact | Per-persona "what's in it for me" (Impact engine v2, `?refresh=1`) |
| POST | /clusters/{id}/ask | Ask a free-text question about a story (Wave B) |
| GET | /clusters/{id}/frameworks | Analytical frameworks for a story (Wave B) |
| GET | /clusters/{id}/consensus | Consensus / divergence across sources (Wave B) |
| GET | /clusters/{id}/timeline | "How we got here" — temporal cluster edges (Wave D2) |
| GET | /clusters/{id}/entities | Entities in a story — cast strip, personalized ranking (G1/G2) |
| GET | /entities/{id}/clusters | Other stories featuring an entity — "appears in" rail (G1) |
| GET | /clusters/{id}/strategic | Game-theory lens (geopolitics-gated) |
| GET | /clusters/{id}/trivia | Story quiz (easy/medium/hard) |
| GET | /trivia/daily | Daily quiz by topic |
| GET/POST/DELETE | /follows[ /{id}] | List / add / remove a follow (topic, entity, saved search, or source) (Wave C; `kind=source` value = source id) |
| GET | /digest | Personalized digest of followed topics/entities (Wave C) |
| GET/POST | /admin/sources | List / upsert sources (research/expert require credibility_score, 0-100 → else 400) |
| PUT | /admin/sources/{id}/credibility | Admin applies a score + rationale; stamps reviewed_by="admin" (400 out-of-range, 404 unknown) |
| GET | /search | Hybrid semantic + keyword search (G2 within-tier relevance boost) |
| GET | /auth/me | Current authenticated user (Firebase) |

**Not yet implemented:** `GET /events` (SSE stream), `GET /admin/breadth`

## Data Pipeline

1. **RSS Fetcher** (every 10 min) → feedparser → dedup → articles table
2. **GDELT Fetcher** (every 15 min) → GDELT API → trafilatura extraction → dedup → articles table
3. **Embedding Backfill** (every 5 min) → Gemini gemini-embedding-001 (768-dim) → pgvector
4. **Clustering** (every 10 min) → pgvector cosine distance (threshold 0.15) → story_clusters table
5. **Entity Extraction Backfill** (every 15 min, on by default via `GRAPH_EXTRACTION_ENABLED`; needs a platform LLM key, skips gracefully without one) → LLM extraction over settled clusters → entities / entity_aliases / article_entities (G1)
6. **Credibility Review** (monthly, 03:00 on the 1st) → propose-only LLM pass over gated rows unreviewed >90d → writes `credibility_meta.proposed_score` + `reviewed_by="llm-proposed"`; never touches the live score, preserves the admin lock, no-ops without a platform LLM key
7. **PubMed Ingest** (weekly, Mon 04:00; gated by `PUBMED_ENABLED`) → NCBI E-utilities → recent abstracts for each medical profession as gated research articles (`audience=["medicine"]`), deduped by PMID, ≤3 req/s
8. **arXiv Generate** (weekly, Mon 04:30) → maps subscribed-topic interests to arXiv categories and idempotently ensures those research sources

## Key Patterns

- **Dedup:** Same-source = URL match + title similarity (rapidfuzz > 0.9). Cross-source similar titles are cluster candidates, NOT duplicates.
- **Embedding status:** Articles have `embedding_status` enum (pending/complete/failed). Backfill job retries pending/failed.
- **Free-first sorting:** Source cards in deep-dive sorted by `is_paywalled` (free first, paywalled last).
- **Explore/exploit:** Feed is 70% exploit (user's topics) + 30% explore (new topics). Ratio adjusts 10-50% based on feedback.
- **G1 entity backbone:** LLM extraction (gated by `GRAPH_EXTRACTION_ENABLED`) populates `entities` / `entity_aliases` / `article_entities`. Resolution is exact-then-alias on normalized (`*_norm`) columns with plain b-tree indexes (no functional `lower()` index — avoids autogenerate drift). No embedding NN / auto-merge in G1 (deferred). Cast strip = `GET /clusters/{id}/entities`; reverse "appears in" rail = `GET /entities/{id}/clusters`.
- **G2 per-user overlay + personalization:** `follows.entity_id` + the RLS-scoped `user_entity_relevance` table capture per-user affinity (follow + positive feedback → `bump_relevance`), decayed at read time (half-life `exp(-ln2·age/half_life)`, age clamped ≥0). One shared scorer `entities.score_clusters_relevance` (= `AVG(decayed)`, no salience term → zero-signal users are a no-op) personalizes the cast strip, feed (recency+relevance blend over a bounded pool), briefing (additive into story_weights), and search (within-tier boost). Gated by `UER_ENABLED` (on by default); each surface is byte-identical when off.
- **Source expansion (research/expert tiers + gating):** `SourceType` adds `research` / `expert`. Gated sources carry `credibility_score` (0-100), `audience` tags, `author_name`, `is_preprint`, `per_fetch_cap`. `audience.allowed_source_ids(tags, floor, followed_source_ids)` shows a gated source only to a matching profession or a follower, above a credibility floor (feed 55 / briefing 70, config `credibility_feed_floor` / `credibility_briefing_floor`). `resolve_tags()` is keyword-map fast path → LLM classifier fallback (fixed tag vocab, cached per user on `persona_version`; no key → keyword-only). News (NULL credibility) is never floored. `SourceTierBadge` renders the tier on StoryCard / SourceCard / DiscoverCard; `BriefingStory` carries a `tier` field. `_upsert_sources` admin-lock: a row with `credibility_meta.reviewed_by=="admin"` survives the 10-min seed re-upsert. `POST /admin/sources` requires `credibility_score` for research/expert (400) and validates 0-100. `sources.json` is a 117-source union (45 gated).
- **Credibility ranking + briefing bonus:** feed rank multiplies by `×(0.9 + 0.2·score/100)` bounded to `[0.9, 1.1]` (NULL news → neutral `credibility_rank_neutral=75`); briefing adds `credibility_briefing_bonus=0.15` into `story_weights` for a persona-matched gated cluster. Both are curation nudges that can't drown fresher news.
- **Follow a source (opt-in):** `follows.kind="source"` (value = source id, no migration). `allowed_source_ids` gains an OR-followed branch that bypasses BOTH the floor and the audience match. `FollowButton` supports the `source` kind on SourceCard. Discover deck reserves up to `discover_gated_slots=5` gated cards.
- **Personal research feeds (Phase 3, backend-only):** PubMed (`pubmed.py`, weekly) maps a medical profession to a search term and ingests recent abstracts as gated research articles; arXiv (`arxiv_gen.py`, weekly) maps subscribed-topic interests to arXiv categories and ensures those sources. Credibility review (`credibility.py`, monthly) is propose-only (writes `proposed_score`, preserves the admin lock). Research-tier clusters get entity extraction at 1 source (`graph_extract_research_min_sources=1`); news keeps the min-2 "settled" bar.
- **BYOM (multi-provider LLM):** `generate()` resolves the per-user `active_provider` → Gemini/OpenAI/Anthropic, model via `model_prefs` JSONB → config default (env default `gemini`). Per-provider Fernet-encrypted keys in `user_settings`; env keys are the platform fallback for background jobs. Embeddings run on Gemini (`gemini-embedding-001`). Anthropic uses assistant-prefill `"{"` for deterministic JSON.
- **Auth + RLS:** `get_current_user` verifies the Firebase ID token and sets `SET LOCAL app.user_id` per request; RLS policies on per-user tables are enforce-when-set (permissive for background jobs). `AUTH_REQUIRED=false` falls back to the default user (single-user dev). RLS only bites under a non-superuser DB role (`backend/scripts/create_app_role.sql`); the explicit `current_user_id()` filter is the primary control. A startup `check_rls_posture` logs a warning when the connection is a superuser.
- **Graceful degradation:** LLM generation degrades by provider — a user with any one valid provider key keeps working if another is down. Summaries fail soft: `get_cluster` / `get_briefing` call `summarize_cluster` on demand when a cluster lacks a cached summary (logged, no user-facing error). If embeddings lag, articles ingest without them and fall back to snippet discovery.
- **Per-user API key:** Fernet-encrypted in `user_settings` (OpenAI/Gemini/Anthropic). Falls back to the matching `*_API_KEY` env var if no per-user key.
- **Capacitor static export:** `BUILD_TARGET=capacitor` triggers `output: "export"` in next.config.ts. Dynamic routes like `[clusterId]` don't work in static export, so Capacitor uses `/story?id=X` query-param routing instead.
- **Dual story routes:** `/story/[clusterId]` for web (dynamic route with rewrites), `/story?id=X` for Capacitor (static export with `useSearchParams` + Suspense boundary).

## Design System

Always read `design-system.md` before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Implementation lives in `frontend/src/app/globals.css`.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match design-system.md.

Key tokens: dark bg `#0C0C0E`, accent amber `#F97316`, fonts **Fraunces** (display/wordmark — the app's override of the kit's Instrument Serif) + DM Sans (body) + JetBrains Mono (data). Brand assets come from the official NewsLens brand kit (single source of truth); see design-system.md → "Brand & App Identity".

## Windows ARM Notes

This project is developed on Windows 11 ARM (win32/arm64). Several tools have compatibility issues:

- **Next.js:** Turbopack is not supported on ARM. Always use `--webpack` flag (already configured in package.json scripts).
- **Backend:** `greenlet` DLL load failure breaks SQLAlchemy async on native Windows ARM. Run backend in Docker instead.
- **Android emulator:** Does not work on Windows ARM — QEMU2 can't run ARM64 guest images on x86_64 host binary (via WOW64), and x86_64 guests need Intel/AMD hardware virtualization. Use a physical Android device for testing.
- **JDK:** Capacitor Android builds require JDK 21 (JDK 17 insufficient).
- **Icon/splash generation:** `sharp`/`@capacitor/assets` don't load on Windows ARM (QEMU amd64 emulation segfaults libvips), and the current `@capacitor/assets` emits broken adaptive output (dangling `@mipmap/ic_launcher_background`, undersized 48px foregrounds). Regenerate launcher icons + splash deterministically via PowerShell `System.Drawing` (high-quality resize) from the official brand kit — never hand-edit the per-density PNGs.

## Mobile / Android Build

NewsLens uses Capacitor to produce a native Android APK from the Next.js static export.

**Build pipeline:**
1. `BUILD_TARGET=capacitor` env var triggers static export mode in `next.config.ts`
2. `NEXT_PUBLIC_API_BASE_URL=http://10.0.2.2:8000` points to host machine from Android emulator/device
3. `next build --webpack` generates static HTML/JS/CSS in `frontend/out/`
4. `npx cap sync android` copies `out/` into the Android WebView project
5. `cd android && ./gradlew assembleDebug` produces the APK

**Quick commands:**
```bash
cd frontend && npm run build:android   # Steps 1-4 combined
cd frontend && npm run apk:debug      # Step 5
# Output: frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

**Capacitor config:** `frontend/capacitor.config.ts` — appId: `com.newslens.app`, webDir: `out`, `SplashScreen` plugin (`launchAutoHide: false` → controlled fade; `SplashScreen.tsx` calls `hide()` on native).

**After building, verify on a physical device** (no emulator on Windows ARM) — see the [on-device checklist in CONTRIBUTING.md](CONTRIBUTING.md#on-device-verification-after-an-android-build).

## Build & Validation

**IMPORTANT:** After every code change, validate the build succeeds.

```bash
# Backend validation
cd backend && python -m py_compile app/main.py   # Quick syntax check
cd backend && pytest -x                           # Run tests, stop on first failure

# Frontend validation
cd frontend && npm run build                      # Full production build (uses --webpack)
cd frontend && npx vitest run                     # Run unit tests
cd frontend && npm run lint:copy                  # Copy guard — blocks internal jargon in UI (see docs/content/COPY-GUIDELINES.md)

# Full stack validation
docker-compose up -d db                           # Ensure DB is running
cd backend && alembic upgrade head                # Apply migrations
cd backend && uvicorn app.main:app --reload &     # Start backend
cd frontend && npm run dev &                      # Start frontend
# Visit http://localhost:3000 and verify feed loads
```
