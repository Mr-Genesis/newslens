# NewsLens

An AI-powered news intelligence platform. NewsLens ingests articles from RSS feeds and the GDELT API, deduplicates them, embeds them with OpenAI, and clusters related coverage into single **stories** — so you read one multi-source briefing instead of ten near-identical headlines.

> Two-language stack: a Python **FastAPI** backend (data pipeline + ML) and a TypeScript **Next.js** frontend (UI), talking over REST JSON. Mobile ships as a native Android app via **Capacitor** wrapping the Next.js static export.

## Features

- **Daily briefing** — top story clusters with AI-generated summaries, free sources surfaced first.
- **Discover deck** — swipe through randomized cards; swipes adjust your topic weights.
- **Deep dive** — every cluster expands to all its source articles with a confidence score (`src:N · coh:0.XX`).
- **Explore/exploit feed** — 70% your topics, 30% new ones; the ratio adapts to your feedback.
- **Bring your own key** — per-user OpenAI API key, Fernet-encrypted, with an env-var fallback.
- **Graceful degradation** — if OpenAI is down, articles still ingest and the UI shows snippets instead of AI summaries.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS 4, Framer Motion |
| Backend | Python, FastAPI, APScheduler |
| Database | PostgreSQL + pgvector |
| ML | OpenAI `text-embedding-3-small`, pgvector cosine clustering |
| Mobile | Capacitor (Android) + `@capacitor/splash-screen` |

## Quick start

Requires Docker (recommended for the DB + backend) and Node.js for the frontend.

```bash
# 1. Configure environment
cp .env.example .env        # then fill in DATABASE_URL, OPENAI_API_KEY, ENCRYPTION_KEY

# 2. Start the database + backend
docker-compose up -d db      # PostgreSQL + pgvector
cd backend && alembic upgrade head
uvicorn app.main:app --reload   # http://localhost:8000

# 3. Start the frontend (separate terminal)
cd frontend && npm install
npm run dev                  # http://localhost:3000
```

Open http://localhost:3000 and the briefing should load. The frontend proxies `/api/*` to the backend via Next.js rewrites, so no CORS setup is needed in web mode.

> **Windows ARM note:** the backend's `greenlet` dependency fails to load natively — run the backend in Docker. Next.js Turbopack is also unsupported on ARM, so all scripts use the `--webpack` flag. See [CLAUDE.md](CLAUDE.md) for the full list of platform caveats.

## Data pipeline

Four APScheduler jobs run inside the FastAPI process:

1. **RSS fetcher** (every 10 min) → feedparser → dedup → `articles`
2. **GDELT fetcher** (every 15 min) → trafilatura extraction → dedup → `articles`
3. **Embedding backfill** (every 5 min) → OpenAI embeddings → pgvector
4. **Clustering** (every 10 min) → pgvector cosine distance (threshold 0.15) → `story_clusters`

## Mobile (Android)

```bash
cd frontend
npm run build:android   # static export + Capacitor sync
npm run apk:debug       # build debug APK via Gradle
# Output: frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

`npm run build:android:prod` points the APK at the deployed backend instead of localhost. Requires JDK 21. The Android emulator does not work on Windows ARM — test on a physical device.

The app ships the official NewsLens brand: an adaptive launcher icon and a cold-start splash (the mark + "NewsLens" wordmark on `#0C0C0E`) that `@capacitor/splash-screen` holds until the web app paints, then cross-fades into the in-app splash. After building, walk the [on-device verification checklist](CONTRIBUTING.md#on-device-verification-after-an-android-build).

## Testing

```bash
cd backend && pytest          # backend API + encryption tests
cd frontend && npx vitest run # frontend unit tests
cd frontend && npx playwright test  # E2E
```

## Documentation

| Doc | What's in it |
|-----|--------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System, pipeline, and DB diagrams; decision log |
| [DEPLOY.md](DEPLOY.md) | Deploying to Render or Fly.io; env var reference |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Developer onboarding + on-device APK verification checklist |
| [design-system.md](design-system.md) | Colors, typography, spacing — read before any UI change |
| [ROADMAP.md](ROADMAP.md) / [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) | Feature roadmap + known limitations |
| [CLAUDE.md](CLAUDE.md) | Commands, architecture notes, platform caveats |

## License

No license file is present — all rights reserved by default. Add a `LICENSE` if you intend this to be open source.
