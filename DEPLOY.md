# Deploying NewsLens

## Option A: Render (recommended for free tier)

### 1. Prerequisites
- GitHub repo pushed to `main` or `master`
- Render account at https://dashboard.render.com

### 2. Database Setup

Render's free Postgres does **not** include pgvector. Two options:

**Option 1 — Neon (free pgvector):**
1. Create a free database at https://neon.tech
2. Enable pgvector: run `CREATE EXTENSION IF NOT EXISTS vector;` in the SQL console
3. Copy the connection string (starts with `postgresql://`)

**Option 2 — Supabase (free pgvector):**
1. Create a free project at https://supabase.com
2. pgvector is pre-installed
3. Copy the connection string from Settings > Database

### 3. Deploy the Backend

1. Go to https://dashboard.render.com > **New > Web Service**
2. Connect your GitHub repo
3. Settings:
   - **Root Directory:** `backend`
   - **Runtime:** Docker
   - **Dockerfile Path:** `./Dockerfile`
   - **Plan:** Free
4. Environment variables:
   - `DATABASE_URL` — paste the Neon/Supabase connection string (the app auto-converts `postgresql://` to `postgresql+asyncpg://`)
   - `GEMINI_API_KEY` — your Google Gemini key (**required**: powers embeddings *and* generation — with no key, embeddings never run → nothing clusters → the feed/briefing stay empty while `/health` is green)
   - `GENERATION_PROVIDER=gemini` — run summaries + lenses on Gemini (default; per-user `active_provider` still wins)
   - `OPENAI_API_KEY` — *optional*, only if you select the OpenAI generation provider (not used for embeddings)
   - `ENCRYPTION_KEY` — a **Fernet** key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (a plain "random string" is rejected by Fernet). Set it **once** and store it — rotating it orphans every stored encrypted key.
   - `INIT_DB_CREATE_ALL=false` — prod schema is Alembic-only (see **Migrations** below)
5. Click **Deploy**. The container runs `alembic upgrade head` on start, then serves. **If the database already exists from a pre-Alembic deploy, do the one-time [reconcile](#reconcile-an-existing-pre-alembic-database) first** or the boot-time upgrade fails.

### 4. Verify

```bash
curl https://your-app.onrender.com/health
# Expected: {"status":"ok","db":true}

curl https://your-app.onrender.com/briefing
# Expected: JSON with stories array
```

### 5. Update Capacitor APK

```bash
cd frontend

# Update the API base URL
# Edit .env.local or set environment variable:
export NEXT_PUBLIC_API_BASE_URL=https://your-app.onrender.com

# Rebuild
npm run build:android
npm run apk:debug
```

The APK at `android/app/build/outputs/apk/debug/app-debug.apk` will now connect to your public backend.

---

## Option B: Fly.io

### 1. Install flyctl
```bash
# Windows
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"

# Or via npm
npm install -g @anthropic-ai/fly
```

### 2. Launch
```bash
cd backend
fly launch --name newslens-api --region iad --no-deploy

# Create Postgres (includes pgvector)
fly postgres create --name newslens-db --region iad
fly postgres attach newslens-db

# Set secrets
fly secrets set OPENAI_API_KEY=sk-...
fly secrets set ENCRYPTION_KEY=$(openssl rand -hex 32)

# Deploy
fly deploy
```

### 3. Verify
```bash
fly open /health
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string (auto-converts to asyncpg) |
| `GEMINI_API_KEY` | **Yes** | Google Gemini key — powers **embeddings** (`gemini-embedding-001`, 768-dim → clustering) *and* the default generation provider |
| `GEMINI_MODEL` | No | Gemini generation model (default `gemini-2.5-flash` — `gemini-2.0-flash` is retired/404s; embedding model is fixed at `gemini-embedding-001`) |
| `GENERATION_PROVIDER` | No | Default generation provider: `gemini` \| `openai` \| `anthropic` (per-user `active_provider` wins) |
| `OPENAI_API_KEY` | No | *Optional* — only for the OpenAI generation provider. **Not used for embeddings.** |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | No | Anthropic platform fallback + model (default `claude-haiku-4-5`) |
| `ENCRYPTION_KEY` | Yes | Fernet key (`Fernet.generate_key()` — 32-byte url-safe base64) for per-user API key storage. Set once; rotating it orphans stored keys |
| `INIT_DB_CREATE_ALL` | No | `false` in prod (schema is Alembic-only). Default `true` bootstraps dev/test via `create_all` |
| `FIREBASE_CREDENTIALS_JSON` *or* `GOOGLE_APPLICATION_CREDENTIALS` | No | Service account to verify Firebase ID tokens. Omit both → auth disabled (default user) |
| `AUTH_REQUIRED` | No | `true` rejects unauthenticated requests (multi-user prod). Default `false` |
| `GRAPH_EXTRACTION_ENABLED` | No | Entity-extraction backfill job (G1). **On by default**; needs a platform LLM key, skips without one. Set `false` to avoid the extraction LLM cost |
| `UER_ENABLED` | No | Per-user entity-relevance personalization (G2). **On by default**; `false` disables it |
| `NCBI_API_KEY` | No | *Optional*, free — only raises the NCBI E-utilities rate ceiling for the weekly PubMed research feed. Without it the job still runs, self-throttled to ≤3 req/s. Get one at https://www.ncbi.nlm.nih.gov/account/settings/ |
| `PUBMED_ENABLED` | No | Weekly PubMed research-abstract ingestion for medical professions. **On by default**; `false` disables it |
| `REQUIRE_ENCRYPTION` | No | `true` refuses to store secrets without `ENCRYPTION_KEY` (recommended in prod) |
| `RSS_FETCH_INTERVAL_MINUTES` | No | RSS fetch interval (default: 10) |
| `GDELT_FETCH_INTERVAL_MINUTES` | No | GDELT fetch interval (default: 15) |
| `EMBEDDING_BACKFILL_INTERVAL_MINUTES` | No | Embedding backfill interval (default: 5) |

> Tuning knobs (`UER_*` blend ratios, `GRAPH_*` extraction params, clustering thresholds) have sensible
> defaults in `backend/app/config.py` and rarely need overriding — see that file for the full list.

## Reconcile an existing (pre-Alembic) database

The deploy runs `alembic upgrade head` on every start (the backend Docker start command). That is safe
for a **fresh** database and a **no-op** once the DB is at head. But a database first built by the old
`init_db` `create_all` path has **no `alembic_version` row** and a schema frozen at whatever code
created it — so a plain `alembic upgrade head` tries to re-`CREATE` tables that already exist and
**fails on boot**. Reconcile it **once**, before (or together with) the first migration-running deploy.

> ⚠️ `op.add_column` is **not idempotent** — it raises `DuplicateColumn` and halts the whole upgrade
> mid-chain if a column already exists. Know the real schema before you upgrade; do not guess.

1. **Snapshot first.** Back up the DB (Render: *Backups → Create*; Neon: a branch; Supabase: a
   snapshot). There is no automatic down-path if an upgrade halts mid-chain.
2. **Probe the real schema** with psql against the prod DB:
   ```sql
   \d users
   SELECT to_regclass('alembic_version');   -- NULL ⇒ never Alembic-managed
   ```
3. **Choose the path:**
   - **At the 4-column baseline** (`users` has only `id, profession, locale, created_at`, no
     `alembic_version`) — it matches baseline `f76aec9da324`, so stamp it there and roll forward (every
     later migration is additive `ADD COLUMN` / `CREATE TABLE`):
     ```bash
     alembic stamp f76aec9da324 && alembic upgrade head
     ```
   - **Partially drifted** (some, not all, post-baseline columns present) — a baseline stamp + upgrade
     would hit `DuplicateColumn`. Hand-apply only the missing delta, then mark it at head:
     ```sql
     ALTER TABLE users ADD COLUMN IF NOT EXISTS watchlist JSONB;
     ALTER TABLE users ADD COLUMN IF NOT EXISTS region VARCHAR(64);
     -- ...remaining missing columns, read off the migration files...
     ```
     ```bash
     alembic stamp head
     ```
   - **Already at head** (full schema + an `alembic_version` row) — nothing to do; the automatic
     upgrade is a no-op.
4. **Verify.** Restart/redeploy and confirm a previously-failing authed route returns 200 — e.g.
   `curl https://<app>.onrender.com/feed` or `/clusters/1` (**not** `/auth/me`: with `AUTH_REQUIRED=false`
   it 500s on drift but never returns a clean 401, so it is a poor probe). Check the next deploy's logs
   for the Alembic `Running upgrade` lines.

Run these from a shell holding the prod `DATABASE_URL` (a Render service shell, or `docker run` the
image with `DATABASE_URL` set). Alembic uses the sync (psycopg2) driver, derived automatically from it.

## Notes

- **Free tier sleep:** Render free tier spins down after 15 min of inactivity. First request takes ~30s to cold-start.
- **pgvector:** Required for embeddings and clustering. Neon and Supabase both offer free pgvector. Render's built-in Postgres does not.
- **Migrations:** run **automatically** on every deploy — the backend Docker start command is `alembic upgrade head && uvicorn …`, so the schema can never drift behind the code (a failed migration blocks startup rather than serving a broken schema). The baseline migration also enables pgvector and builds the entity-graph + per-user tables + RLS policies. A database that predates Alembic must be [reconciled once first](#reconcile-an-existing-pre-alembic-database), or the boot-time upgrade fails.
- **Source expansion (Phases 1–3):** the only schema change is the Phase 1 migration `b2c3d4e5f6a7` (Source credibility/audience columns) — it is already in the chain, so the existing alembic-on-deploy step applies it with no extra action. Phases 2 and 3 (badges, ranking, follow-source, credibility ops, PubMed/arXiv research feeds) added **no** further migration.
- **Multi-user auth (optional):** Set `FIREBASE_CREDENTIALS_JSON` (inline service-account JSON works well for hosted secrets) and `AUTH_REQUIRED=true`. Without it, the app runs single-user (every request is the default user).
- **Row-level security:** RLS on per-user tables only *enforces* under a non-superuser DB role — create one with `backend/scripts/create_app_role.sql` and point `DATABASE_URL` at it for real multi-tenant isolation. A startup check logs a warning if the connection is a superuser. (The explicit per-user query filter is always on regardless.)
- **Personalization:** Entity-relevance personalization (G2) is on by default and safe — a brand-new account with no signal sees the neutral ranking. Set `UER_ENABLED=false` to turn it off. Populating the entity graph also needs `GRAPH_EXTRACTION_ENABLED=true` + a platform LLM key.
- **Source-expansion LLM jobs:** the monthly credibility review (propose-only) and the audience LLM classifier (fallback for professions the keyword map misses) both need a platform LLM key. Without one they **no-op** — the review proposes nothing and audience resolution falls back to keyword-only. Credibility scores are set only by seed data or the admin endpoint (`PUT /admin/sources/{id}/credibility`); the review job never mutates a live score on its own.
- **Graceful degradation:** Generation works with any one provider key (Gemini/OpenAI/Anthropic); summaries generate on demand if a batch missed them; without embeddings, discovery falls back to snippets and keyword matching. **Embeddings require the Gemini key** (`gemini-embedding-001`).
