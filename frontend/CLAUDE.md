# Frontend — CLAUDE.md

Frontend-specific guidance for Claude Code. See also `../CLAUDE.md` for full-stack context.

## Stack

Next.js 16 App Router, React 19, Tailwind CSS 4, Framer Motion, Capacitor (Android).

**Important:** Always use `--webpack` flag for builds — Turbopack is broken on Windows ARM. This is already configured in `package.json` scripts.

## Pages

| Route | File | Purpose |
|-------|------|---------|
| `/` | `app/page.tsx` | Briefing screen — daily AI news briefing |
| `/discover` | `app/discover/page.tsx` | Discover screen — swipable card deck |
| `/story/[clusterId]` | `app/story/[clusterId]/page.tsx` | Deep dive — web (dynamic route) |
| `/story?id=X` | `app/story/page.tsx` + `StoryContent.tsx` | Deep dive — Capacitor (query param) |
| `/settings` | `app/settings/page.tsx` | Settings — OpenAI API key management |

### Why two story routes?

Next.js static export (`output: "export"`) cannot handle dynamic route segments like `[clusterId]` without `generateStaticParams`. Since cluster IDs are dynamic and unknown at build time, Capacitor builds use `/story?id=X` with `useSearchParams` instead. Web builds use the dynamic route with API proxy rewrites.

## Component Hierarchy

```
layout.tsx (NavBar)
├── page.tsx → StoryCard[]
├── discover/page.tsx → DiscoverCard[] (Framer Motion swipe)
├── story/[clusterId]/page.tsx → DeepDiveView → SourceCard[], AISummaryBox
├── story/page.tsx → StoryContent → DeepDiveView
└── settings/page.tsx
```

## API Client

`src/lib/api.ts` — Environment-aware base URL:
- Web: `/api` (proxied to backend via Next.js rewrites in `next.config.ts`)
- Capacitor: `NEXT_PUBLIC_API_BASE_URL` env var (e.g., `http://10.0.2.2:8000`)

## Design System

Visual specs live in `../design-system.md`. CSS token implementation in `src/app/globals.css`.

Key tokens: dark bg `#0C0C0E`, accent amber `#F97316`, fonts Instrument Serif (display) + DM Sans (body) + JetBrains Mono (data).

## Capacitor / Static Export

`next.config.ts` is conditional based on `BUILD_TARGET` env var:
- **Web mode** (default): API rewrites `/api/*` → `localhost:8000`
- **Capacitor mode** (`BUILD_TARGET=capacitor`): `output: "export"`, no rewrites

Build commands:
```bash
npm run build:android    # Static export + cap sync
npm run apk:debug       # Gradle assembleDebug
```
