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

## Code Style

- **Python:** Enforced by `ruff` — run `cd backend && ruff check .`
- **TypeScript:** Enforced by ESLint — run `cd frontend && npm run lint`
- **CSS:** Tailwind CSS utility classes. Design tokens defined in `design-system.md`, implemented in `frontend/src/app/globals.css`

## Project Structure

See `CLAUDE.md` for the full directory tree, API endpoints, and architectural decisions.
See `ARCHITECTURE.md` for system diagrams and database schema.
See `design-system.md` for visual design specifications.
