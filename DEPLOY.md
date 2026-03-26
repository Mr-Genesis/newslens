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
| `OPENAI_API_KEY` | No | OpenAI API key (summaries/embeddings degrade gracefully without it) |
| `ENCRYPTION_KEY` | Yes | Fernet encryption key for per-user API key storage |
| `RSS_FETCH_INTERVAL_MINUTES` | No | RSS fetch interval (default: 10) |
| `GDELT_FETCH_INTERVAL_MINUTES` | No | GDELT fetch interval (default: 15) |
| `EMBEDDING_BACKFILL_INTERVAL_MINUTES` | No | Embedding backfill interval (default: 5) |

## Notes

- **Free tier sleep:** Render free tier spins down after 15 min of inactivity. First request takes ~30s to cold-start.
- **pgvector:** Required for embeddings and clustering. Neon and Supabase both offer free pgvector. Render's built-in Postgres does not.
- **Graceful degradation:** The app works without OpenAI — summaries fall back to snippets, topic assignment falls back to keyword matching.
