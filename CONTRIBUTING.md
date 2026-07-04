# Contributing — NewsLens

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 20+ | Frontend runtime |
| Python | 3.11+ | Backend runtime |
| Docker | Latest | Required for PostgreSQL + pgvector (and backend on Windows ARM) |
| JDK | 21 | Only needed for Android APK builds |

## Local Setup

### 1. Database

```bash
docker-compose up -d db
# PostgreSQL + pgvector on localhost:5432
```

### 2. Backend

```bash
cd backend
cp ../.env.example ../.env          # Edit with your values
pip install -r requirements.txt
alembic upgrade head                # Run migrations
uvicorn app.main:app --reload       # http://localhost:8000
```

> **Windows ARM:** Backend must run in Docker due to greenlet DLL failure.
> Use `docker-compose up` instead (starts both DB and backend).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                         # http://localhost:3000
```

The frontend proxies `/api/*` to `localhost:8000` via Next.js rewrites — no CORS setup needed.

### 4. Environment Variables

Copy `.env.example` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | Yes | Database password |
| `OPENAI_API_KEY` | No | Platform fallback key — also the only provider used for embeddings (users can set their own in Settings) |
| `ENCRYPTION_KEY` | Prod | Fernet key for encrypting the per-user API keys stored in `user_settings` |
| `GENERATION_PROVIDER` | No | Default LLM provider for generation: `openai` \| `anthropic` \| `gemini` (per-user `active_provider` wins) |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | No | Platform fallback keys for the other providers (background jobs) |
| `FIREBASE_CREDENTIALS_JSON` *or* `GOOGLE_APPLICATION_CREDENTIALS` | No | Service account to verify Firebase ID tokens. Omit both → auth disabled, requests use the default user (single-user dev) |
| `AUTH_REQUIRED` | No | `true` rejects unauthenticated requests with 401 (multi-user prod). Default `false` |
| `GRAPH_EXTRACTION_ENABLED` | No | Entity-extraction backfill job (G1). **On by default**; needs a platform LLM key (skips without one). Set `false` to disable |
| `UER_ENABLED` | No | Per-user entity-relevance personalization (G2). **On by default**; `false` disables it everywhere |
| `NCBI_API_KEY` | No | PubMed (NCBI E-utilities) key for the weekly research-ingest cron. Raises the rate ceiling; the job self-throttles either way and runs unauthenticated without it |
| `PUBMED_ENABLED` | No | PubMed research-ingest cron (maps a medical persona → search term → gated research articles). **On by default**; `false` disables ingestion |

> **Source-expansion knobs (Phase 1-3):** the credibility floors (`credibility_feed_floor` 55 /
> `credibility_briefing_floor` 70 — below the floor a gated source is discover/search-only or kept out of
> the briefing), `discover_gated_slots` (5 reserved research/expert cards in the discover deck),
> `graph_extract_research_min_sources` (1 — research clusters are singletons, so they get entity extraction
> without the news min-2 "settled" bar), `credibility_review_stale_days` (90 — monthly LLM re-proposal
> window) and the `pubmed_*` throttle/retmax all have working defaults in `backend/app/config.py`.
> Each is the uppercased field name as an env var (`env_prefix=""`). Override in `.env` only to tune;
> **don't duplicate the full list here — read `config.py`.**

Generate an encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Migrations note:** `alembic upgrade head` also creates the entity-graph tables
> (`entities`, `entity_aliases`, `article_entities`, `user_entity_relevance`, `follows`,
> `cluster_edges`) and installs the row-level-security policies on the per-user tables. RLS only
> *enforces* under a non-superuser DB role (`backend/scripts/create_app_role.sql`); the dev/superuser
> role bypasses it, so the explicit `current_user_id()` filter is the primary isolation control.

## Running Tests

```bash
# Backend
cd backend && pytest                # All tests
cd backend && pytest -x             # Stop on first failure
cd backend && pytest -v             # Verbose output

# Frontend
cd frontend && npx vitest run       # Unit tests
cd frontend && npx playwright test  # E2E tests (requires running servers)
```

> **Source-expansion suites (Phase 1-3):** the research/expert tiers, persona gating, credibility
> ranking, PubMed/arXiv ingest and the credibility-ops endpoints are covered under
> `backend/tests/unit/` (`test_audience.py`, `test_pubmed_adapter.py`, `test_arxiv_gen.py`,
> `test_config_g2.py`) and `backend/tests/integration/` (`test_source_expansion.py`, the
> `test_phase2_*.py` ranking/discover/follow-source/filter tests, and the `test_phase3_*.py`
> credibility-ops/pubmed/arxiv/classifier/entity-relax tests). Run the whole thing with `pytest`.

## Building Android APK

```bash
cd frontend
npm run build:android               # Static export + Capacitor sync
npm run apk:debug                  # Gradle build
# Output: android/app/build/outputs/apk/debug/app-debug.apk
```

> **Windows ARM:** Android emulator doesn't work. Test on a physical device by transferring the APK.

> The launcher icon, web/PWA favicons, and splash images come from the official NewsLens brand kit and are generated **deterministically** (PowerShell `System.Drawing` high-quality resize) — `sharp`/`@capacitor/assets` don't load on Windows ARM, and the current `@capacitor/assets` emits broken adaptive output. Regenerate via that pipeline; don't hand-edit the per-density PNGs.

## On-Device Verification (after an Android build)

The Android emulator does not run on Windows ARM, so a built APK must be checked on a **physical device**. After `npm run build:android && npm run apk:debug`, install `frontend/android/app/build/outputs/apk/debug/app-debug.apk` (USB transfer or `adb install`) and walk this checklist:

**Launcher icon**
- [ ] Shows the NewsLens mark (square brackets + amber dot) on the dark `#0C0C0E` tile — not the old generic / Android-robot icon.
- [ ] Under every shape the launcher applies (circle, squircle, rounded square), the mark stays centered and is **not cropped** — the adaptive safe zone holds.
- [ ] Crisp at launcher, app-switcher, and Settings → Apps sizes (per-density assets, no upscaling blur).

**Cold-start splash**
- [ ] A cold launch shows the mark + "NewsLens" wordmark centered on `#0C0C0E`.
- [ ] No white/black flash before the splash paints (brand-dark window background).
- [ ] The native splash holds until the app is ready, then cross-fades (~250 ms) into the in-app splash — no hard cut or blank gap.
- [ ] Renders centered in both portrait and landscape.

**First-run & loading**
- [ ] `/welcome` → `/onboarding` reads as one flow (same mono eyebrow + italic Fraunces headline); welcome slide 1 shows the framed spotlight (mark in a ring with outer source ticks).
- [ ] Opening a story shows a content-shaped skeleton (title / summary / source rows), not a generic spinner.

**Smoke**
- [ ] Briefing, Discover, and a Deep Dive load against the configured backend (`build:android` → `http://10.0.2.2:8000`; `build:android:prod` → the deployed backend).

**Hardware back button (WS-4 · #114)** — no emulator on Windows ARM, so verify on the device:
- [ ] Open a story (Today → tap) then press **hardware back** → returns to the previous screen (pop), not the launcher.
- [ ] Switch to a non-home tab (Discover / Saved / Search / Profile), press **back** → lands on **Today** in one hop (not walking back through prior tab switches).
- [ ] Switch tabs a few times, then press **back** repeatedly → each press goes to Today / exits cleanly, never replaying the tab-switch history.
- [ ] On **Today**, press **back** → a toast **"Press back again to exit"** appears; a second back within 2 s **minimizes** the app (Today reappears on relaunch with state intact); the app is **never killed/exited**.
- [ ] Cold-start a deep link / notification into a story, press **back** with no history → same toast + double-press-to-minimize (does not blank or crash).

## Code Style

- **Python:** Enforced by `ruff` — run `cd backend && ruff check .`
- **TypeScript:** Enforced by ESLint — run `cd frontend && npm run lint`
- **CSS:** Tailwind CSS utility classes. Design tokens defined in `design-system.md`, implemented in `frontend/src/app/globals.css`

## Project Structure

See `CLAUDE.md` for the full directory tree, API endpoints, and architectural decisions.
See `ARCHITECTURE.md` for system diagrams and database schema.
See `design-system.md` for visual design specifications.
