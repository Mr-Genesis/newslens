# Frontend — CLAUDE.md

Frontend-specific guidance for Claude Code. See also `../CLAUDE.md` for full-stack context.

## Stack

Next.js 16 App Router, React 19, Tailwind CSS 4, Framer Motion, Capacitor (Android) + `@capacitor/splash-screen`.

**Important:** Always use `--webpack` flag for builds — Turbopack is broken on Windows ARM. This is already configured in `package.json` scripts.

## Pages

| Route | File | Purpose |
|-------|------|---------|
| `/` | `app/page.tsx` | Briefing screen — daily AI news briefing |
| `/welcome` | `app/welcome/page.tsx` | First-run 3-page intro (before onboarding) |
| `/onboarding` | `app/onboarding/page.tsx` | Persona/interest picker (E3) |
| `/login` | `app/login/page.tsx` | Firebase sign-in (Google + Email/Password) |
| `/discover` | `app/discover/page.tsx` | Discover screen — swipable card deck |
| `/search` | `app/search/page.tsx` | Hybrid keyword + semantic search |
| `/following` | `app/following/page.tsx` | Followed topics / entities + digest |
| `/story/[clusterId]` | `app/story/[clusterId]/page.tsx` | Deep dive — web (dynamic route) |
| `/story?id=X` | `app/story/page.tsx` + `StoryContent.tsx` | Deep dive — Capacitor (query param) |
| `/saved` | `app/saved/page.tsx` | Saved articles list with unsave |
| `/settings` | `app/settings/page.tsx` | Profile, topics, theme, multi-provider API keys + model selection |
| `/admin/sources` | `app/admin/sources/page.tsx` | Source management (list / upsert) |

### Why two story routes?

Next.js static export (`output: "export"`) cannot handle dynamic route segments like `[clusterId]` without `generateStaticParams`. Since cluster IDs are dynamic and unknown at build time, Capacitor builds use `/story?id=X` with `useSearchParams` instead. Web builds use the dynamic route with API proxy rewrites.

## Component Hierarchy

```
layout.tsx (NavBar)
├── page.tsx → StoryCard[]
├── discover/page.tsx → DiscoverCard[] (Framer Motion swipe)
├── story/[clusterId]/page.tsx → DeepDiveView → SourceCard[], AISummaryBox,
│                                  EntityChips (cast strip), ImpactCard, AskBox,
│                                  FrameworksCard, ConsensusRow, FollowButton
├── story/page.tsx → StoryContent → DeepDiveView
├── following/page.tsx → FollowButton[]
└── settings/page.tsx (multi-provider key + model UI)
```

Most story lenses (impact / ask / frameworks / consensus) and the entity cast strip self-fetch their
own endpoint and are gated/skeleton-guarded, so the deep-dive renders progressively.

## API Client

`src/lib/api.ts` — Environment-aware base URL:
- Web: `/api` (proxied to backend via Next.js rewrites in `next.config.ts`)
- Capacitor: `NEXT_PUBLIC_API_BASE_URL` env var (e.g., `http://10.0.2.2:8000`)

**Auth:** when Firebase is configured, the client attaches the user's ID token as a Bearer header; the
backend `get_current_user` verifies it and scopes per-user data. With `AUTH_REQUIRED=false` (default
dev) the backend falls back to the default user, so the app works unauthenticated.

## Design System

Visual specs live in `../design-system.md`. CSS token implementation in `src/app/globals.css`.

Key tokens: dark bg `#0C0C0E`, accent amber `#F97316`, fonts **Fraunces** (display/wordmark — overrides the kit's Instrument Serif) + DM Sans (body) + JetBrains Mono (data). Brand assets (icons/splash) come from the official NewsLens brand kit.

## Capacitor / Static Export

`next.config.ts` is conditional based on `BUILD_TARGET` env var:
- **Web mode** (default): API rewrites `/api/*` → `localhost:8000`
- **Capacitor mode** (`BUILD_TARGET=capacitor`): `output: "export"`, no rewrites

Build commands:
```bash
npm run build:android    # Static export + cap sync
npm run apk:debug       # Gradle assembleDebug
```

**Splash:** `@capacitor/splash-screen` holds the native splash (`launchAutoHide: false`, `#0C0C0E`) and `src/components/SplashScreen.tsx` calls `SplashScreen.hide({ fadeOutDuration: 250 })` on native once the web overlay paints — a controlled native-splash → WebView fade. Native splash images + launcher icon come from the official brand kit. Verify on a physical device after building (no emulator on Windows ARM).
