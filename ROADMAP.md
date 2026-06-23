# Roadmap — NewsLens

> **Active plan:** the post-handover differentiation work lives in [`docs/moat/00-PLAN.md`](docs/moat/00-PLAN.md)
> (Waves Q–D) with the Wave A engineering spec in [`docs/moat/01-wave-a-eng-plan.md`](docs/moat/01-wave-a-eng-plan.md).
> This file tracks the older MVP→v2 backlog.

## Current Status

**Working:**
- Data pipeline: RSS + GDELT fetching, dedup, embedding, clustering (all on APScheduler)
- API: ~27 endpoints (feed, briefing, discover, cluster lenses, profile, settings, search, admin, stats)
- Frontend: Briefing, Discover, Deep Dive, Search, Saved, Settings, Onboarding
- Real LLM features shipped (E1–E8): provider abstraction (OpenAI + Gemini), real AI summaries,
  analysis/5Ws/profession lenses, **per-persona Impact engine v2 (structured + guarded, Wave A)**,
  strategic lens, trivia/daily quiz
- Feedback-driven explore/exploit (0.3 is now only a cold-start fallback; swipes move weights)
- Design system: Full spec + CSS token implementation
- Mobile: Capacitor Android APK builds
- Per-user OpenAI + Gemini API key management with Fernet encryption

**Still stubbed / heuristic:**
- Cluster `coherence` is still a source-count heuristic (0.95/0.85/0.75/0.65), not a learned score —
  the UI now labels it honestly ("Source overlap"), and a real consensus/divergence metric is Wave B
- Tension lines on discover cards still fall back to article titles when no AI line exists

---

## Phase 1: Core AI (High Priority)

These fill the biggest MVP gaps — the app functions but lacks its AI intelligence core.

### 1.1 AI Summaries
Replace hardcoded coherence scores and stub summaries with real GPT-4o-mini calls in `/briefing` and `/discover/deck`. Config already exists in `backend/app/config.py` (`summary_model`, `summary_batch_size`).

### 1.2 Dynamic Explore/Exploit Ratio
Implement feedback-driven adjustment of the explore ratio. Currently hardcoded at 0.3 in config. Should analyze recent feedback (window of 50) to shift between 0.1-0.5. Infrastructure exists in `user_preferences.weight` and `user_preferences.breadth_score`.

### 1.3 SSE Events Endpoint
Implement `GET /events` for real-time feed updates. Events: `new_article`, `new_cluster`, `feed_refresh`. Library `sse-starlette` is already in requirements. Frontend would subscribe on mount for live updates.

---

## Phase 2: Production Readiness (Medium Priority)

### 2.1 Deploy Backend Publicly
Required for the APK to work on real devices (currently points to `10.0.2.2:8000` which only works in emulator). Options: Fly.io, Render, or Railway. Docker setup already exists.

### 2.2 Admin Endpoints
Implement `GET /admin/sources` (source health: last fetch time, error rate, article count) and `GET /admin/breadth` (evaluation metrics: topic coverage, source diversity).

### 2.3 Test Coverage Gaps
Current tests cover API layer + encryption + settings. Missing:
- `test_fetcher.py` — RSS parsing, error handling
- `test_gdelt.py` — GDELT API integration
- `test_dedup.py` — URL match + fuzzy title dedup
- `test_clustering.py` — pgvector distance thresholds
- `test_briefing.py` — Briefing endpoint with real clusters
- `test_discover.py` — Discover deck generation + swipe recording

### 2.4 Run Skillchain Domains
76 skills across 10 domains installed in `~/.claude/commands/skillchain/`. Run security, frontend, backend, devops, infrastructure, developer, data, ai-ml skillchains for comprehensive project analysis. Requires fresh Claude Code session (commands loaded at startup).

---

## Phase 3: Polish (Lower Priority)

### 3.1 AI Tension Lines
Generate compelling "tension line" for discover cards using GPT — the core conflict of a story in one sentence. Currently falls back to article title.

### 3.2 Topic Auto-Assignment
Automatically categorize articles into topics using embedding similarity. Currently topics exist in the schema but aren't auto-populated.

### 3.3 Pull-to-Refresh
Implement in briefing screen. Full spec exists in `design-system.md` (threshold: 60px, rubber-band resistance curve, accent spinner).

### 3.4 Orientation Handling
Landscape card sizing per design-system.md: `min(360px, 60vh)` card height, percentage-based swipe thresholds.

### 3.5 Custom App Icon
Replace default Capacitor launcher icon with NewsLens branding. Current icon is the default Android bot.

---

## Known Limitations

| Issue | Workaround | Root Cause |
|-------|------------|------------|
| Turbopack doesn't work | `--webpack` flag in all npm scripts | Windows ARM not supported |
| Backend can't run natively on Windows ARM | Run in Docker | greenlet DLL load failure breaks SQLAlchemy async |
| Android emulator doesn't work | Use physical device or skip | QEMU2 + WOW64 incompatibility on ARM |
| Dynamic routes fail in Capacitor build | Dual routing: `[clusterId]` (web) + `?id=X` (Capacitor) | Next.js static export can't handle dynamic segments |
| JDK 17 insufficient for Capacitor | JDK 21 required | Capacitor Android Gradle config targets Java 21 |
