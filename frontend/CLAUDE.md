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
├── page.tsx → StoryCard[] (SourceTierBadge)
├── discover/page.tsx → DiscoverCard[] (Framer Motion swipe; SourceTierBadge + "Follow source")
├── story/[clusterId]/page.tsx → DeepDiveView → SourceCard[] (SourceTierBadge + FollowButton source),
│                                  AISummaryBox, EntityChips (cast strip), ImpactCard, AskBox,
│                                  FrameworksCard, ConsensusRow, FollowButton
├── story/page.tsx → StoryContent → DeepDiveView
├── following/page.tsx → FollowButton[]
└── settings/page.tsx (multi-provider key + model UI)
```

Most story lenses (impact / ask / frameworks / consensus) and the entity cast strip self-fetch their
own endpoint and are gated/skeleton-guarded, so the deep-dive renders progressively.

### Source tier badges + follow-source (Phase 2 · #78/#81/#83)

`SourceTierBadge` (`components/ui/SourceTierBadge.tsx`) renders provenance for gated sources:
`research → RESEARCH`, `expert → EXPERT · <author> · <score>`, plus a `PREPRINT · not peer-reviewed`
chip. A plain news source (or a NULL/unknown tier) renders **nothing**, so news cards are visually
unchanged. Used on `StoryCard` (via `story.tier`), `SourceCard`, and `DiscoverCard`.

`FollowButton` (`components/ui/FollowButton.tsx`) takes a `kind` of `topic | entity | saved_search |
source`. The `source` kind (value = the source id) powers a "Follow source" control on `SourceCard`
and on gated `DiscoverCard`s — following a source opts you into its tier past the credibility/audience
gate.

## API Client

`src/lib/api.ts` — Environment-aware base URL:
- Web: `/api` (proxied to backend via Next.js rewrites in `next.config.ts`)
- Capacitor: `NEXT_PUBLIC_API_BASE_URL` env var (e.g., `http://10.0.2.2:8000`)

**Caching (PR #127):** `src/lib/cache.ts` is a two-tier stale-while-revalidate cache (in-memory `Map` +
IndexedDB via `idb-keyval`) behind the `useCachedResource` hook. The briefing (`page.tsx`), story detail
(`DeepDiveView`), and feed page-1 (`useInfiniteFeed`) paint the last-known response **instantly**, then
revalidate in the background — masking the free-tier cold start and killing the refetch on every "back
to home". Per-namespace TTL + oldest-first eviction; `usePrefetchClusters` warms the top-3 story details
so a tap opens instantly. When adding a new cached surface, key it as `<namespace>:<id>` and reuse the
hook — never hand-roll a fetch-in-`useState`.

**Auth:** when Firebase is configured, the client attaches the user's ID token as a Bearer header; the
backend `get_current_user` verifies it and scopes per-user data. With `AUTH_REQUIRED=false` (default
dev) the backend falls back to the default user, so the app works unauthenticated.

**Source-tier fields (Phase 2):** `Source` carries `source_type` / `author_name` / `credibility_score`
/ `is_preprint`; `BriefingStory` carries `tier`; `DiscoverCard` carries `source_id` / `source_type` /
`is_gated` / `is_preprint` / `author_name` / `credibility_score` (all null/omitted for plain news).
`getFeed(page?, perPage?, topicId?, sourceType?)` passes `source_type=news|research|expert`
(`"all"`/omitted = every tier). **Deferred:** the `#82` filter-chip UI is not built — `/feed` has no
rendered screen yet, so only the `getFeed` param shipped.

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

## Back-behavior guideline (WS-4 · #114)

Android hardware back and tab history are handled in exactly two places, **native-only** (gated by `Capacitor.isNativePlatform()` — web keeps stock browser semantics, so the browser back button never exits the site):

- **`src/components/BackButtonHandler.tsx`** (mounted once in `layout.tsx`) owns the hardware back:
  - **Real history anywhere** (a stacked screen like `/story`, a settings sub-screen) → `router.back()` (pop).
  - **Non-home tab root** (Discover / Saved / Search / Following / Profile) → `router.replace("/")` — one hop to Today.
  - **Empty history anywhere** — home (Today), OR a deep-linked / cold-started non-root route with no history → toast **"Press back again to exit"**, second press within 2 s → `App.minimizeApp()`. **Never `App.exitApp()`.**
- **`src/components/layout/BottomTabBar.tsx`** — tab navigations use `router.replace` on native (tabs never stack history) and `<Link>` push on web.

Rules when adding a route:
- **Classify every new route.** If it's a bottom-tab destination, add it to `src/lib/navRoots.ts` `TAB_ROOTS` (the shared set both files read — they must not drift). Otherwise it's a stacked screen and just pops.
- **`ROOTS` matter ONLY for the hop-to-Today / minimize branches.** Any route with real history just pops — you don't need to touch anything.
- **Stacked navigations use `push`; tab-bar navigations use `replace`.** Don't push a tab (it would stack history and make back walk through tab switches).
- The shared **`NavBar`** renders a back control (→ `router.back()`) on non-root deep-dive routes; **do not add a "← Back" header to a tab root** — the tab bar is its navigation.
