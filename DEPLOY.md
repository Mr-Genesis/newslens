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
   - `OPENAI_API_KEY` — your OpenAI API key
   - `ENCRYPTION_KEY` — any random 32+ char string (for Fernet key encryption)
5. Click **Deploy**

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
| `OPENAI_API_KEY` | No* | OpenAI key — *required for embeddings/clustering* and the platform generation fallback |
| `ENCRYPTION_KEY` | Yes | Fernet encryption key for per-user API key storage |
| `GENERATION_PROVIDER` | No | Default generation provider: `openai` \| `anthropic` \| `gemini` (per-user `active_provider` wins) |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | No | Google Gemini platform fallback + model |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | No | Anthropic platform fallback + model (default `claude-haiku-4-5`) |
| `FIREBASE_CREDENTIALS_JSON` *or* `GOOGLE_APPLICATION_CREDENTIALS` | No | Service account to verify Firebase ID tokens. Omit both → auth disabled (default user) |
| `AUTH_REQUIRED` | No | `true` rejects unauthenticated requests (multi-user prod). Default `false` |
| `GRAPH_EXTRACTION_ENABLED` | No | Entity-extraction backfill job (G1). Off by default; needs a platform LLM key |
| `UER_ENABLED` | No | Per-user entity-relevance personalization (G2). **On by default**; `false` disables it |
| `REQUIRE_ENCRYPTION` | No | `true` refuses to store secrets without `ENCRYPTION_KEY` (recommended in prod) |
| `RSS_FETCH_INTERVAL_MINUTES` | No | RSS fetch interval (default: 10) |
| `GDELT_FETCH_INTERVAL_MINUTES` | No | GDELT fetch interval (default: 15) |
| `EMBEDDING_BACKFILL_INTERVAL_MINUTES` | No | Embedding backfill interval (default: 5) |

> Tuning knobs (`UER_*` blend ratios, `GRAPH_*` extraction params, clustering thresholds) have sensible
> defaults in `backend/app/config.py` and rarely need overriding — see that file for the full list.

## Notes

- **Free tier sleep:** Render free tier spins down after 15 min of inactivity. First request takes ~30s to cold-start.
- **pgvector:** Required for embeddings and clustering. Neon and Supabase both offer free pgvector. Render's built-in Postgres does not.
- **Migrations:** `alembic upgrade head` creates all tables (incl. the entity-graph + per-user tables) and installs the RLS policies. Run it once against the deployment DB.
- **Multi-user auth (optional):** Set `FIREBASE_CREDENTIALS_JSON` (inline service-account JSON works well for hosted secrets) and `AUTH_REQUIRED=true`. Without it, the app runs single-user (every request is the default user).
- **Row-level security:** RLS on per-user tables only *enforces* under a non-superuser DB role — create one with `backend/scripts/create_app_role.sql` and point `DATABASE_URL` at it for real multi-tenant isolation. A startup check logs a warning if the connection is a superuser. (The explicit per-user query filter is always on regardless.)
- **Personalization:** Entity-relevance personalization (G2) is on by default and safe — a brand-new account with no signal sees the neutral ranking. Set `UER_ENABLED=false` to turn it off. Populating the entity graph also needs `GRAPH_EXTRACTION_ENABLED=true` + a platform LLM key.
- **Graceful degradation:** Generation works with any one provider key (OpenAI/Anthropic/Gemini); summaries generate on demand if a batch missed them; without embeddings, discovery falls back to snippets and keyword matching. **Embeddings always require OpenAI.**
