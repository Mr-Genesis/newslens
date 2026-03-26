# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Backend (Python FastAPI)
cd backend && pip install -r requirements.txt   # Install backend deps
cd backend && uvicorn app.main:app --reload     # Start backend dev server (port 8000)
cd backend && pytest                            # Run backend tests
cd backend && alembic upgrade head              # Run database migrations
cd backend && alembic revision --autogenerate -m "description"  # Create new migration

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

**Stack:** Next.js 16 App Router, React 19, Tailwind CSS 4, Framer Motion, Python FastAPI, PostgreSQL + pgvector, OpenAI API, APScheduler, Capacitor (Android)

**Key architectural decisions:**
- pgvector nearest-neighbor SQL for clustering (not Python pairwise — O(n) vs O(n²))
- APScheduler (AsyncIOScheduler) inside FastAPI process for cron jobs
- Next.js `rewrites` in `next.config.ts` proxying `/api/*` → `localhost:8000` (no CORS needed in web mode)
- `rapidfuzz` for title dedup (10-100x faster than python-Levenshtein)
- `asyncpg` (not psycopg2) to preserve FastAPI's async benefits
- Single-user MVP with `user_id` FK for forward-compatibility
- Per-user OpenAI API key with Fernet encryption + env var fallback
- Capacitor static export with conditional `next.config.ts` (`BUILD_TARGET=capacitor`)
- Dual story routes: `/story/[clusterId]` (web dynamic) + `/story?id=X` (Capacitor static export)

## Directory Structure

```
news-app/
├── backend/                           # Python FastAPI backend
│   ├── app/
│   │   ├── main.py                   # FastAPI app, lifespan, scheduler setup
│   │   ├── config.py                 # Pydantic settings (env vars)
│   │   ├── database.py               # SQLAlchemy async engine + session
│   │   ├── models.py                 # SQLAlchemy ORM models (9 tables)
│   │   ├── schemas.py                # Pydantic request/response schemas
│   │   ├── api/
│   │   │   └── routes.py             # All REST endpoints
│   │   └── services/
│   │       ├── fetcher.py            # RSS feed fetcher (feedparser + httpx)
│   │       ├── gdelt.py              # GDELT API integration (URL discovery + trafilatura)
│   │       ├── dedup.py              # Deduplication (URL match + rapidfuzz title similarity)
│   │       ├── embeddings.py         # OpenAI embedding generation + backfill
│   │       ├── clustering.py         # pgvector nearest-neighbor story clustering
│   │       └── encryption.py         # Fernet encryption for per-user API keys
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
│   │   │   │   └── page.tsx          # OpenAI API key management
│   │   │   └── story/
│   │   │       ├── [clusterId]/
│   │   │       │   └── page.tsx      # Deep dive (web — dynamic route)
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
│   │   │       └── Skeleton.tsx      # Loading skeleton shimmer
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

**Not yet implemented:** `GET /events` (SSE stream), `GET /admin/sources`, `GET /admin/breadth`

## Data Pipeline

1. **RSS Fetcher** (every 10 min) → feedparser → dedup → articles table
2. **GDELT Fetcher** (every 15 min) → GDELT API → trafilatura extraction → dedup → articles table
3. **Embedding Backfill** (every 5 min) → OpenAI text-embedding-3-small → pgvector
4. **Clustering** (every 10 min) → pgvector cosine distance (threshold 0.15) → story_clusters table

## Key Patterns

- **Dedup:** Same-source = URL match + title similarity (rapidfuzz > 0.9). Cross-source similar titles are cluster candidates, NOT duplicates.
- **Embedding status:** Articles have `embedding_status` enum (pending/complete/failed). Backfill job retries pending/failed.
- **Free-first sorting:** Source cards in deep-dive sorted by `is_paywalled` (free first, paywalled last).
- **Explore/exploit:** Feed is 70% exploit (user's topics) + 30% explore (new topics). Ratio adjusts 10-50% based on feedback.
- **Graceful degradation:** If OpenAI is down, articles ingested without embeddings; UI shows snippet instead of AI summary.
- **Per-user API key:** Fernet-encrypted in `user_settings` table. Falls back to `OPENAI_API_KEY` env var if no per-user key.
- **Capacitor static export:** `BUILD_TARGET=capacitor` triggers `output: "export"` in next.config.ts. Dynamic routes like `[clusterId]` don't work in static export, so Capacitor uses `/story?id=X` query-param routing instead.
- **Dual story routes:** `/story/[clusterId]` for web (dynamic route with rewrites), `/story?id=X` for Capacitor (static export with `useSearchParams` + Suspense boundary).

## Design System

Always read `design-system.md` before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Implementation lives in `frontend/src/app/globals.css`.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match design-system.md.

Key tokens: dark bg `#0C0C0E`, accent amber `#F97316`, fonts Instrument Serif (display) + DM Sans (body) + JetBrains Mono (data).

## Windows ARM Notes

This project is developed on Windows 11 ARM (win32/arm64). Several tools have compatibility issues:

- **Next.js:** Turbopack is not supported on ARM. Always use `--webpack` flag (already configured in package.json scripts).
- **Backend:** `greenlet` DLL load failure breaks SQLAlchemy async on native Windows ARM. Run backend in Docker instead.
- **Android emulator:** Does not work on Windows ARM — QEMU2 can't run ARM64 guest images on x86_64 host binary (via WOW64), and x86_64 guests need Intel/AMD hardware virtualization. Use a physical Android device for testing.
- **JDK:** Capacitor Android builds require JDK 21 (JDK 17 insufficient).

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

**Capacitor config:** `frontend/capacitor.config.ts` — appId: `com.newslens.app`, webDir: `out`

## Build & Validation

**IMPORTANT:** After every code change, validate the build succeeds.

```bash
# Backend validation
cd backend && python -m py_compile app/main.py   # Quick syntax check
cd backend && pytest -x                           # Run tests, stop on first failure

# Frontend validation
cd frontend && npm run build                      # Full production build (uses --webpack)
cd frontend && npx vitest run                     # Run unit tests

# Full stack validation
docker-compose up -d db                           # Ensure DB is running
cd backend && alembic upgrade head                # Apply migrations
cd backend && uvicorn app.main:app --reload &     # Start backend
cd frontend && npm run dev &                      # Start frontend
# Visit http://localhost:3000 and verify feed loads
```
