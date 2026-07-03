# NewsLens

An AI-powered news intelligence platform. NewsLens ingests articles from RSS feeds and the GDELT API, deduplicates them, embeds them with Gemini, and clusters related coverage into single **stories** — so you read one multi-source briefing instead of ten near-identical headlines.

> Two-language stack: a Python **FastAPI** backend (data pipeline + ML) and a TypeScript **Next.js** frontend (UI), talking over REST JSON. Mobile ships as a native Android app via **Capacitor** wrapping the Next.js static export.

## Features

- **Daily briefing** — top story clusters with AI-generated summaries, free sources surfaced first.
- **Discover deck** — swipe through randomized cards; swipes adjust your topic weights.
- **Deep dive** — every cluster expands to all its source articles with a confidence score (`src:N · coh:0.XX`).
- **Story lenses** — Key Facts / 5Ws, a profession-aware "what's in it for me" impact, ask-a-question, analytical frameworks, consensus/divergence, a "how we got here" timeline, and a per-story quiz.
- **Who's in the story** — a cast strip of the people/orgs/places in each cluster, with an "appears in" rail to other stories about the same entity.
- **Personalized ranking** — follow entities and read stories, and the entities you care about rise across the cast strip, feed, briefing, and search. On by default; a brand-new account just sees the neutral ranking.
- **Research + expert sources** — beyond news, a curated union of **research** (journals, preprints) and **expert** tiers, each with a credibility score (0-100) and provenance badges (`RESEARCH` / `EXPERT · author · score` / `PREPRINT · not peer-reviewed`). Gated tiers are shown only to a matching profession or a follower, above a credibility floor, and nudge feed ranking and the briefing.
- **Personal research feeds** — a doctor's specialty pulls recent **PubMed** abstracts; your subscribed topics generate matching **arXiv** feeds — both ingested as gated research and surfaced through the same persona gate.
- **Follows + digest** — follow topics, entities, saved searches, **or a source** (opt in to a gated source and it bypasses the floor and audience match for you) and get a personalized digest.
- **Bring your own model** — per-user, Fernet-encrypted keys for **Gemini, OpenAI, or Anthropic**, with model selection and an env-var platform fallback. (Embeddings use Gemini `gemini-embedding-001`.)
- **Accounts** — Firebase auth (Google + Email/Password); single-user dev mode when auth isn't configured.
- **Graceful degradation** — generation degrades by provider (any one valid key keeps you working); summaries generate on demand if a batch missed them; if embeddings lag, the UI falls back to snippets.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS 4, Framer Motion |
| Backend | Python, FastAPI, APScheduler, Firebase Admin SDK (auth) |
| Database | PostgreSQL + pgvector (+ row-level security on per-user tables) |
| ML | Gemini `gemini-embedding-001` (embeddings, 768-dim) + multi-provider generation (Gemini / OpenAI / Anthropic); pgvector cosine clustering |
| Mobile | Capacitor (Android) + `@capacitor/splash-screen` |

## Quick start

Requires Docker (recommended for the DB + backend) and Node.js for the frontend.

```bash
# 1. Configure environment
cp .env.example .env        # fill in GEMINI_API_KEY (embeddings + generation) (+ ENCRYPTION_KEY for production).
                            # Optional: OPENAI_API_KEY / ANTHROPIC_API_KEY (other generation providers),
                            # FIREBASE_CREDENTIALS_JSON + AUTH_REQUIRED (multi-user auth),
                            # GRAPH_EXTRACTION_ENABLED / UER_ENABLED (entity graph + personalization),
                            # PUBMED_ENABLED + NCBI_API_KEY (personal PubMed research feed)

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

APScheduler jobs run inside the FastAPI process:

1. **RSS fetcher** (every 10 min) → feedparser → dedup → `articles`
2. **GDELT fetcher** (every 15 min) → trafilatura extraction → dedup → `articles`
3. **Embedding backfill** (every 5 min) → Gemini embeddings (`gemini-embedding-001`) → pgvector
4. **Clustering** (every 10 min) → pgvector cosine distance (threshold 0.15) → `story_clusters`
5. **Entity extraction** (every 15 min, on by default behind `GRAPH_EXTRACTION_ENABLED`; needs a platform LLM key, skips gracefully without one) → LLM extraction over settled clusters → `entities` / `article_entities`. Research-tier clusters extract at a single source (news keeps the min-2 "settled" bar).
6. **Credibility review** (monthly) → propose-only: an LLM suggests a `proposed_score` for gated sources unreviewed >90 days, never touching the live score or the admin lock.
7. **PubMed ingest** (weekly, Mon 04:00) → NCBI E-utilities → recent abstracts for each medical profession among your users, ingested as gated research.
8. **arXiv sources** (weekly, Mon 04:30) → maps subscribed-topic interests to arXiv categories and idempotently ensures the matching research feeds.

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
