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
| `OPENAI_API_KEY` | No | Global fallback API key (users can set their own in Settings) |
| `ENCRYPTION_KEY` | Yes | Fernet key for encrypting per-user API keys |

Generate an encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

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

## Code Style

- **Python:** Enforced by `ruff` — run `cd backend && ruff check .`
- **TypeScript:** Enforced by ESLint — run `cd frontend && npm run lint`
- **CSS:** Tailwind CSS utility classes. Design tokens defined in `design-system.md`, implemented in `frontend/src/app/globals.css`

## Project Structure

See `CLAUDE.md` for the full directory tree, API endpoints, and architectural decisions.
See `ARCHITECTURE.md` for system diagrams and database schema.
See `design-system.md` for visual design specifications.
