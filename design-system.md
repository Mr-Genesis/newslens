# Design System — NewsLens

## Product Context
- **What this is:** AI-powered news intelligence platform with daily briefings, swipable discovery, and multi-source deep dives
- **Who it's for:** News-savvy readers who want breadth not bubbles, multi-perspective views, and free-first source sorting
- **Space/industry:** News aggregation, AI-assisted journalism tools
- **Project type:** Mobile-first web app (3 screens: Briefing, Discover, Deep Dive)

## Aesthetic Direction
- **Direction:** Editorial/Industrial — "The Intelligence Brief"
- **Visual thesis:** A redacted intelligence briefing that leaked onto your phone — matte surfaces, sharp typography, warm amber as the single chromatic accent
- **Decoration level:** Minimal — typography and spacing do all the work. No hero images, no decorative blobs, no gradient fills
- **Mood:** Quiet authority. The feeling of walking into a calm operations room where someone competent already triaged the noise. Data density treated as luxury, not clutter
- **Core principle:** Monochromatic until the user interacts — color is earned through action, not decoration
- **Anti-patterns:** No purple gradients, no 3-column icon grids, no centered everything, no uniform bubbly border-radius, no stock photo hero sections

## Typography
- **Display/Hero:** Instrument Serif (italic) — editorial broadsheet elegance with hand-set quality. Used for all headlines, story titles, briefing headers
- **Body:** DM Sans — geometric sans with warmth. Slightly wider than typical UI fonts for a declassified-document feel. Used for summaries, descriptions, UI text
- **UI/Labels:** DM Sans (same as body, 500 weight for emphasis)
- **Data/Tables:** JetBrains Mono — tabular figures, ligatures make data feel intentional. Used for timestamps, source counts, confidence scores, metadata
- **Code:** JetBrains Mono
- **Loading:** Google Fonts CDN — `https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300..700;1,9..40,300..700&family=JetBrains+Mono:wght@400;500&display=swap`
- **Scale:**
  - Hero: 28px / 1.2 line-height / -0.02em tracking (Instrument Serif italic)
  - Title: 22px / 1.3 line-height / -0.01em tracking (Instrument Serif italic)
  - Heading: 17px / 1.35 line-height (Instrument Serif italic)
  - Body: 15px / 1.7 line-height (DM Sans)
  - Small: 13px / 1.5 line-height (DM Sans)
  - Caption: 12px / 1.4 line-height (DM Sans)
  - Mono: 11px / 1.6 line-height / 0.05em tracking (JetBrains Mono)
  - Category label: 12px / uppercase / 0.15em tracking (Instrument Serif)

## Color

### Approach: Restrained
One chromatic accent (warm amber) + monochrome neutrals. Semantic colors appear only during interaction.

### Dark Mode (default)
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#0C0C0E` | Page background (near-black, blue undertone) |
| `--surface` | `#18181B` | Card/panel surface |
| `--surface-raised` | `#27272A` | Active states, modals, swipe card face |
| `--surface-hover` | `#2E2E33` | Hover states |
| `--text-primary` | `#E4E4E7` | Headlines, body text (87% white) |
| `--text-secondary` | `#A1A1AA` | Secondary content, summaries |
| `--text-muted` | `#71717A` | Timestamps, metadata |
| `--text-ghost` | `#3F3F46` | Dimmed/paywalled content, redacted hints |
| `--accent` | `#F97316` | Warm amber — unread dots, active feedback, breaking badge |
| `--accent-muted` | `#7C2D12` | Accent backgrounds behind accent text |
| `--accent-subtle` | `rgba(249,115,22,0.08)` | Accent hover fills |
| `--signal` | `#22D3EE` | Cyan — new cluster formed, new signal detected |
| `--agree` | `#4ADE80` | Green — swipe right, FREE badge, success |
| `--dismiss` | `#EF4444` | Red — swipe left, error (brief edge glow only) |
| `--drill` | `#A78BFA` | Violet — swipe up, deep dive entry, AI summary box |
| `--warning` | `#FACC15` | Yellow — low confidence, caution states |
| `--agree-muted` | `rgba(74,222,128,0.12)` | Badge/alert backgrounds |
| `--dismiss-muted` | `rgba(239,68,68,0.12)` | Badge/alert backgrounds |
| `--drill-muted` | `rgba(167,139,250,0.12)` | AI summary box background |
| `--border` | `#27272A` | 1px borders, structural |
| `--border-subtle` | `#1E1E22` | Hairline separators |

### Light Mode
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#FAFAF9` | Warm stone background |
| `--surface` | `#FFFFFF` | Cards |
| `--surface-raised` | `#F4F4F5` | Active/hover |
| `--text-primary` | `#18181B` | Body text |
| `--text-secondary` | `#52525B` | Secondary |
| `--text-muted` | `#A1A1AA` | Metadata |
| `--text-ghost` | `#D4D4D8` | Dimmed |
| `--accent` | `#EA580C` | Slightly deeper amber |
| `--border` | `#E4E4E7` | Borders |

## Spacing
- **Base unit:** 8px
- **Density:** Comfortable — generous vertical rhythm, content breathes
- **Scale:** 2xs(2px) xs(4px) sm(8px) md(16px) lg(24px) xl(32px) 2xl(48px) 3xl(64px)
- **Horizontal padding:** 16px on mobile (full-bleed cards)
- **Vertical story separation:** 1px hairline border + 32px gap
- **Category section gap:** 24px top margin

## Layout
- **Approach:** Single-column, full-bleed, content as continuous document
- **Grid:** Single column at all breakpoints (mobile-first, max-width constrains on desktop)
- **Max content width:** 640px (reading-optimized)
- **Border radius:** Hierarchical — sm:4px (badges, buttons), md:8px (cards, inputs), lg:12px (modals, phone frames)
- **Card style:** No visible card borders on mobile — separated by 1px hairlines and vertical space. Cards feel like a continuous document, not a deck of objects
- **Navigation:** 3-segment progress indicator at top (3px tall, amber for active segment). Briefing | Discover | Deep Dive

## Motion
- **Approach:** Intentional — motion serves comprehension and tactile feedback, never decoration
- **Easing:**
  - Enter: ease-out (content appearing)
  - Exit: ease-in (content departing)
  - Move: cubic-bezier(0.16, 1, 0.3, 1) — fast start, slow finish, no bounce (swipe cards)
- **Duration:**
  - Micro: 50-100ms (button press, badge appear)
  - Short: 150-250ms (hover states, color transitions)
  - Medium: 250-400ms (card transitions, skeleton shimmer)
  - Long: 400-700ms (page transitions, swipe card departure)

### Swipe Card Physics
- **Inertia:** High — 4px dead zone before card moves (sensation of "unsticking" something weighty)
- **Follow:** Zero lag after dead zone, decelerate on cubic-bezier(0.16, 1, 0.3, 1)
- **Rotation:** Max 8° tilt at full swipe (deliberate, not playful). Pivot at bottom of card
- **Commit threshold:** 40% of screen width
- **Feedback:** 2px edge glow in semantic color (green right, red left, violet up), intensifies with distance. At commit: glow expands to 6px soft shadow
- **Departure:** Card accelerates off-screen, slight opacity fade to 0.8
- **Swipe up (drill):** Card scales 1.0→1.02 over 200ms, then content cross-fades into Deep Dive. Violet pulse from card center
- **Next card reveal:** Already visible at 8px below, 0.97 scale, 0.95 opacity. Steps forward on departure: 300ms ease-out to full size/opacity

## Component Patterns

### Story Card (Briefing)
- Unread amber dot (6px) before title
- Title in Instrument Serif italic (17px)
- 1-2 sentence summary in DM Sans (14px, secondary color)
- Metadata row: `src:N` in accent, `coh:0.XX` in muted, relative time in ghost
- 1px hairline separator, 32px vertical gap between stories

### Discover Card (Swipe)
- No images — text-only cards
- Topic badge (top-right, colored by category)
- Tension line: single sentence in Instrument Serif italic (22px) — the core conflict
- 3 bullet sourced facts in DM Sans (14px)
- Footer: source names (mono 11px) + confidence score (mono 11px ghost)
- Stack: 3 cards visible (top active, 2 behind at 0.97/0.94 scale, 0.6/0.3 opacity)

### Source Card (Deep Dive)
- Free sources: full opacity, green "FREE" badge (mono 11px, agree-muted background)
- Paywalled sources: 0.5 opacity, orange "PAYWALL" badge (mono 11px, dismiss-muted background)
- Each card: outlet name (DM Sans 13px bold), excerpt (13px secondary), "Read full article →" link (mono 12px, accent color)
- Sorted: free first, then paywalled, alphabetical within each group

### AI Summary Box
- Background: drill-muted (violet tint)
- Left border: 3px solid drill color
- Label: "AI SUMMARY" in mono 11px, drill color
- Body: DM Sans 14px, secondary color
- Disclaimer footer: "AI-generated summary · may contain errors · verify with sources below" in mono 10px, ghost color

### Confidence Display
- Format: `src:N · coh:0.XX` in JetBrains Mono 11px
- When coherence < 0.6: summary text renders with expanded letter-spacing (0.5px) to visually signal looseness
- Color: accent for source count, ghost for coherence

### Navigation
- 3-segment horizontal bar at top of viewport, 3px tall
- Active segment: amber fill
- Inactive segments: surface-raised fill
- Segments represent: Briefing | Discover | Deep Dive
- Brand "NewsLens" in header: Instrument Serif 28px, "News" in primary, "Lens" in accent

### Loading States
- Skeleton shimmer matching content layout
- Shimmer color: surface → surface-raised pulse, 1.5s duration
- First-run empty state: "Setting up your feed..." with animated pulse in accent-subtle

### Error States
- Error message in DM Sans 15px
- "Couldn't load [X]" + retry button (secondary style)
- Error icon: dismiss color, subtle

## Token Architecture

### Tier 1: Global Tokens (raw values)
```css
/* Palette — never reference directly in components */
--gray-950: #0C0C0E;
--gray-900: #18181B;
--gray-800: #27272A;
--gray-750: #2E2E33;
--gray-700: #3F3F46;
--gray-500: #71717A;
--gray-400: #A1A1AA;
--gray-300: #D4D4D8;
--gray-200: #E4E4E7;
--gray-100: #F4F4F5;
--gray-50: #FAFAF9;
--white: #FFFFFF;
--orange-600: #EA580C;
--orange-500: #F97316;
--orange-900: #7C2D12;
--cyan-400: #22D3EE;
--green-400: #4ADE80;
--red-500: #EF4444;
--violet-400: #A78BFA;
--yellow-400: #FACC15;
```

### Tier 2: Semantic Tokens (themes override here)
```css
/* These are the tokens components reference */
--color-bg: var(--gray-950);           /* dark */ | var(--gray-50);    /* light */
--color-surface: var(--gray-900);      /* dark */ | var(--white);      /* light */
--color-surface-raised: var(--gray-800);
--color-text-primary: var(--gray-200); /* dark */ | var(--gray-950);   /* light */
--color-text-secondary: var(--gray-400);
--color-text-muted: var(--gray-500);
--color-text-ghost: var(--gray-700);
--color-accent: var(--orange-500);     /* dark */ | var(--orange-600); /* light */
--color-border: var(--gray-800);
```

### Tier 3: Component Tokens (scoped)
```css
/* Story card */
--story-title-color: var(--color-text-primary);
--story-summary-color: var(--color-text-secondary);
--story-meta-color: var(--color-text-ghost);
--story-unread-color: var(--color-accent);
--story-separator: var(--color-border);

/* Swipe card */
--swipe-card-bg: var(--color-surface-raised);
--swipe-glow-right: var(--color-agree);
--swipe-glow-left: var(--color-dismiss);
--swipe-glow-up: var(--color-drill);

/* Source card */
--source-free-badge-bg: var(--agree-muted);
--source-free-badge-text: var(--color-agree);
--source-paywall-badge-bg: var(--dismiss-muted);
--source-paywall-badge-text: var(--color-dismiss);
--source-link-color: var(--color-accent);

/* AI Summary */
--ai-summary-bg: var(--drill-muted);
--ai-summary-border: var(--color-drill);
--ai-summary-label: var(--color-drill);
--ai-summary-disclaimer: var(--color-text-ghost);

/* Navigation */
--nav-active: var(--color-accent);
--nav-inactive: var(--color-surface-raised);
```

## Accessibility

### Contrast Ratios (WCAG AA)
| Combination | Ratio | Pass |
|-------------|-------|------|
| text-primary (#E4E4E7) on bg (#0C0C0E) | 15.4:1 | ✅ AAA |
| text-secondary (#A1A1AA) on bg (#0C0C0E) | 7.5:1 | ✅ AAA |
| text-muted (#71717A) on bg (#0C0C0E) | 4.0:1 | ✅ AA (large text) |
| text-ghost (#3F3F46) on bg (#0C0C0E) | 2.1:1 | ⚠️ Decorative only |
| accent (#F97316) on bg (#0C0C0E) | 5.9:1 | ✅ AA |
| accent (#F97316) on surface (#18181B) | 5.2:1 | ✅ AA |
| Light: text-primary (#18181B) on bg (#FAFAF9) | 15.8:1 | ✅ AAA |
| Light: accent (#EA580C) on bg (#FAFAF9) | 4.6:1 | ✅ AA |

### Non-Color Indicators
- Swipe direction: edge glow + card movement direction (not just color)
- FREE/PAYWALL: text label + badge, not color alone
- Unread: dot + bold title weight, not just dot color
- Confidence: numeric value shown, not just visual treatment
- Error: text message + icon, not just red color

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  /* Disable swipe physics — snap instead of animate */
  /* Disable skeleton shimmer — static gray */
  /* Disable card stack animations — instant swap */
  /* Keep essential: loading spinners (slowed), focus rings */
}
```

### Touch Targets
- Minimum 44x44px for all interactive elements
- Story cards: full-width tap target
- Swipe cards: full card is gesture target
- Buttons: minimum 44px height, 16px horizontal padding
- Navigation segments: full-width per segment, 48px tap height

## Responsive Breakpoints
| Breakpoint | Width | Layout Changes |
|------------|-------|----------------|
| Mobile (default) | < 640px | Single column, 16px padding, bottom safe area |
| Tablet | 640-1024px | Single column, 24px padding, max-width 640px centered |
| Desktop | > 1024px | Single column, max-width 640px centered, top nav replaces segment bar |

## State Machines

### Briefing Page
```
idle → loading → success | error | empty
error → retrying → success | error
success → refreshing → success | error
```
- **idle:** Initial mount, no data
- **loading:** Skeleton shimmer visible
- **success:** Briefing rendered with stories grouped by category
- **error:** "Couldn't load briefing" + retry button
- **empty:** "Setting up your feed..." pulse animation (first run, no articles yet)
- **refreshing:** Pull-to-refresh, existing content stays visible with subtle opacity

### Discover Page
```
idle → loading_deck → swiping | empty | error
swiping → swiping (card removed, next revealed)
swiping → loading_more (deck < 5 remaining, pre-fetch)
swiping → drilling (swipe up, load topic cards)
drilling → swiping (topic cards inserted)
swiping → empty (deck exhausted)
empty → loading_deck (refresh tapped)
```
- **swiping:** Active card stack, gesture handler enabled
- **loading_more:** Background fetch, no UI change (optimistic)
- **drilling:** Swipe-up expansion animation + topic card fetch
- **empty:** "You're all caught up" + refresh button

### Deep Dive Page
```
idle → loading → success | error
success (rendered) — user scrolls through sources
error → retrying → success | error
```

### Swipe Card (per card)
```
resting → dragging → released
released → committed_right | committed_left | committed_up | returned
committed_right → departing_right → removed
committed_left → departing_left → removed
committed_up → expanding → deep_dive
returned → resting (snap back with spring)
```
- **dragging:** Card follows finger, edge glow intensifies, rotation increases
- **released:** Velocity check — if past commit threshold or high velocity, commit; else return
- **departing_*:** Card accelerates off-screen (400ms ease-in)
- **expanding:** Card scales up 1.02x, cross-fade to Deep Dive (200ms)
- **returned:** Spring animation back to center (300ms ease-out)

## Micro-Interactions

### Swipe Card Gesture
| Phase | Trigger | Feedback | Duration |
|-------|---------|----------|----------|
| Touch start | Finger down on card | 4px dead zone (no movement) | — |
| Drag | Finger moves past dead zone | Card follows, tilt increases, edge glow appears | Continuous |
| Approach threshold | Card at 30% screen width | Edge glow brightens, slight haptic (if available) | — |
| Cross threshold | Card at 40% screen width | Edge glow expands to 6px shadow, haptic pulse | — |
| Release (commit) | Finger up, past threshold | Card accelerates away, opacity fades to 0.8 | 400ms ease-in |
| Release (cancel) | Finger up, before threshold | Card springs back to center | 300ms ease-out |
| Next card | Top card removed | Behind card steps forward: scale 0.97→1, opacity 0.95→1, y 8→0 | 300ms ease-out |

### Pull-to-Refresh (Briefing)
| Phase | Trigger | Feedback | Duration |
|-------|---------|----------|----------|
| Pull start | Scroll past top | Resistance increases (rubber-band) | Continuous |
| Threshold | Pulled 60px | Subtle snap, accent spinner appears | — |
| Release | Finger up past threshold | Spinner animates, content refreshes | Variable |
| Complete | New data loaded | Spinner fades, content updates with stagger | 300ms |

### Unread Dot
| Phase | Trigger | Feedback | Duration |
|-------|---------|----------|----------|
| Appear | New story in briefing | Amber dot fades in at 6px size | 200ms ease-out |
| Persist | Story not tapped | Steady dot, no pulsing (quiet, not demanding) | — |
| Dismiss | Story tapped | Dot fades out | 150ms ease-in |

### Badge Appear (FREE/PAYWALL/Topic)
| Phase | Trigger | Feedback | Duration |
|-------|---------|----------|----------|
| Appear | Card/source enters view | Badge scales from 0.8→1.0, fades in | 150ms ease-out |

### Confidence Warning
| Phase | Trigger | Feedback | Duration |
|-------|---------|----------|----------|
| Low confidence | coherence < 0.6 | Summary text letter-spacing expands 0→0.5px | 200ms ease-out |
| Visual hint | On render | Amber warning badge appears next to coh value | 150ms |

## Feedback Patterns

### Swipe Feedback
- **Right (agree):** Green edge glow (2→6px), card tilts right (0→8°)
- **Left (dismiss):** Red edge glow (2→6px), card tilts left (0→-8°)
- **Up (drill):** Violet edge glow (2→6px), card rises slightly (0→-4px translate-y)
- **Cancel:** Spring back to center, glow fades (300ms)

### Action Confirmations
- **Briefing refresh:** Inline — spinner at top, content updates in place with 50ms stagger per story
- **Swipe recorded:** No toast — the card departure IS the confirmation (optimistic UI)
- **API error:** Inline error at bottom of current view — "Couldn't save preference. Retrying..." in mono 11px, dismiss color, auto-retry 3x then show retry button

### System Status
- **Loading:** Skeleton shimmer (surface → surface-raised pulse, 1.5s, infinite)
- **Empty:** Centered message, DM Sans 15px, muted color, animated accent dot pulse
- **Offline:** Top banner "No connection" in surface-raised bg, mono 11px, dismiss color icon
- **Stale data:** Timestamp in briefing header shows relative time, turns accent color when >4h old

## Elevation

### Z-Index Scale
| Layer | z-index | Usage |
|-------|---------|-------|
| Base | 0 | Page content |
| Cards | 10 | Story cards, source cards |
| Swipe stack | 20-22 | Swipe cards (back:20, middle:21, top:22) |
| Navigation | 30 | Segment bar, header |
| Overlay | 40 | Modals, toasts |
| System | 50 | Error banners, offline indicator |

### Shadow Scale (dark mode — use sparingly)
- **None:** Default for most elements (dark mode uses surface color for depth)
- **Sm:** `0 1px 2px rgba(0,0,0,0.3)` — subtle lift on hover
- **Md:** `0 4px 12px rgba(0,0,0,0.4)` — swipe card at rest
- **Lg:** `0 8px 24px rgba(0,0,0,0.5)` — active/dragging swipe card
- **Glow:** `0 0 Npx var(--semantic-color)` — swipe edge glow (N = 2-6 based on distance)

## Mobile Viewport Specs

### Safe Areas
- Use `viewport-fit=cover` in `<meta name="viewport">` to extend into notch/dynamic island area
- Apply `env(safe-area-inset-top)` and `env(safe-area-inset-bottom)` for padding on affected edges
- CSS pattern: `padding-top: calc(env(safe-area-inset-top, 0px) + 48px)` for navbar clearance
- CSS pattern: `padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 64px)` for bottom safe area

### Device Width Tiers
| Device | Width | Adjustments |
|--------|-------|-------------|
| iPhone SE (3rd gen) | 320px | Hero 24px, category label 11px, card padding 12px, max 2 facts on discover |
| iPhone 12 mini | 375px | Standard sizes per typography scale |
| iPhone 14 | 390px | Standard (reference device) |
| iPhone 14 Pro Max | 430px | Standard, slightly more breathing room |
| Tablet (640-1024px) | 640px+ | 24px horizontal padding, max-width 640px centered |
| Desktop (>1024px) | 1024px+ | Same as tablet, top nav replaces segment bar (future) |

### Orientation
- **Primary:** Portrait
- **Landscape:** Card stack height → `min(360px, 60vh)` to prevent overflow. Swipe commit threshold → `40% * viewport width` (already percentage-based). NavBar remains sticky top.
- **Lock:** No forced orientation lock — graceful adaptation

### Input Detection
```css
@media (pointer: coarse) {
  /* Touch devices: enforce 44px minimum on all interactive elements */
  /* Swipe dead zone: 4px */
}
@media (pointer: fine) {
  /* Mouse/trackpad: no dead zone, hover states enabled */
  /* Swipe dead zone: 0px */
}
```

### Scroll Behavior
- **Briefing:** `scroll-snap-type: y proximity` on the scrollable container. Category section headers as snap points (`scroll-snap-align: start`). Momentum scrolling via `-webkit-overflow-scrolling: touch`.
- **Discover:** No scroll — fixed card stack with gesture control
- **Deep Dive:** Standard vertical scroll, no snap points. Smooth scroll for back-to-top.
- **Settings:** Standard vertical scroll

### Pull-to-Refresh (Briefing)
- Threshold: 60px pull distance
- Resistance curve: `Math.min(distance * 0.4, 80)` — rubber-band effect
- Visual feedback: Accent-colored spinner appears at threshold
- Release: Spinner animates while data refreshes, fades on completion (300ms)

## Per-Screen Layout Specs

### Briefing Screen (`/`)
```
┌─────────────────────────────┐
│ safe-area-inset-top          │
├─────────────────────────────┤
│ NavBar (48px)                │
│ ┌─ 3px progress bar ──────┐ │
├─┴──────────────────────────┴─┤
│ pt: 24px                     │
│ ┌──────────────────────────┐ │
│ │ CATEGORY LABEL (12px)    │ │
│ │ ─────────────────────────│ │
│ │ • Story title (17px)     │ │
│ │   Summary (14px)         │ │
│ │   src:N · coh:0.XX · 2h  │ │
│ │ ─────── hairline ────────│ │
│ │ • Story title (17px)     │ │
│ │   Summary (14px)         │ │
│ │   src:N · coh:0.XX · 5h  │ │
│ └──────────────────────────┘ │
│ mt: 24px                     │
│ ┌──────────────────────────┐ │
│ │ CATEGORY LABEL           │ │
│ │ ...more stories...       │ │
│ └──────────────────────────┘ │
│ pb: safe-area-inset-bottom   │
│     + 64px                   │
└─────────────────────────────┘
```
- **Horizontal padding:** 16px (var(--space-md))
- **Max width:** 640px centered
- **Story separation:** 1px hairline + 32px vertical gap
- **Category gap:** 24px top margin between sections
- **Scroll snap:** Category headers snap to top on scroll proximity
- **320px override:** Hero text 24px (from 28px), category label 11px (from 12px)
- **Focus order:** Skip-to-content → NavBar → Category headers (h2) → Story cards (article elements)
- **Screen reader:** Categories as `role="heading" aria-level="2"`, stories as `<article>` landmarks

### Discover Screen (`/discover`)
```
┌─────────────────────────────┐
│ safe-area-inset-top          │
├─────────────────────────────┤
│ NavBar (48px)                │
├─────────────────────────────┤
│ pt: 24px                     │
│ ┌──────────────────────────┐ │
│ │ ┌────────────────────┐   │ │
│ │ │   [Topic Badge]    │   │ │
│ │ │                    │   │ │
│ │ │ Tension Line (22px)│   │ │
│ │ │                    │   │ │
│ │ │ • Fact 1 (14px)    │   │ │
│ │ │ • Fact 2           │   │ │
│ │ │ • Fact 3           │   │ │
│ │ │ ────────────────── │   │ │
│ │ │ src · coh:0.XX     │   │ │
│ │ └────────────────────┘   │ │
│ │  ┌──────────────────┐    │ │ ← 0.97 scale, 8px below
│ │  └──────────────────┘    │ │
│ │   ┌────────────────┐     │ │ ← 0.94 scale, 16px below
│ │   └────────────────┘     │ │
│ └──────────────────────────┘ │
│ Deck counter: "3 of 25"     │
│ pb: safe-area-inset-bottom   │
└─────────────────────────────┘
```
- **Card stack container:** `height: min(380px, calc(100vh - 200px))` — prevents overflow on short viewports
- **Card height:** `min(360px, calc(100vh - 240px))` — responsive to viewport
- **Card padding:** 24px (p-6) standard, 16px on 320px screens
- **Swipe thresholds:** `40% * viewport width` horizontal, `25% * card height` vertical (replace hardcoded 120px / -100px)
- **320px override:** Tension line 20px (from 22px), max 2 facts (from 3), card padding 16px
- **Reduced motion:** Instant card swap, no physics animation, no tilt/glow
- **Accessibility:** `role="group" aria-label="Discover card deck"`, active card `aria-live="polite"`, keyboard arrows for navigation
- **Stack peek:** 2nd card at 0.97 scale / 0.6 opacity / 8px translateY. 3rd card at 0.94 scale / 0.3 opacity / 16px translateY

### Deep Dive Screen (`/story/[clusterId]`)
```
┌─────────────────────────────┐
│ safe-area-inset-top          │
├─────────────────────────────┤
│ NavBar (48px)                │
├─────────────────────────────┤
│ ← Back (44px tap target)    │
│                              │
│ Story Title (28px hero)      │
│ src:N · coh:0.XX             │
│                              │
│ ┌──────────────────────────┐ │
│ │ AI SUMMARY (violet box)  │ │
│ │ 2-3 sentence summary     │ │
│ │ Disclaimer footer        │ │
│ └──────────────────────────┘ │
│                              │
│ SOURCES  3 free · 1 paywall  │
│ ┌──────────────────────────┐ │
│ │ Reuters [FREE]           │ │
│ │ Excerpt text...          │ │
│ │ Read full article →      │ │
│ ├──────────────────────────┤ │
│ │ BBC News [FREE]          │ │
│ │ Excerpt text...          │ │
│ │ Read full article →      │ │
│ ├──────────────────────────┤ │
│ │ WSJ [PAYWALL] (50% op.)  │ │
│ │ Excerpt text...          │ │
│ │ Read full article →      │ │
│ └──────────────────────────┘ │
│ pb: safe-area-inset-bottom   │
└─────────────────────────────┘
```
- **Back button:** `min-h-[44px]` tap target enforced (currently just text — needs fix)
- **320px override:** AI summary box padding 12px (from 16px), source card text 12px (from 13px)
- **Scroll:** Standard vertical, no snap. Smooth scroll enabled.
- **Screen reader:** AI summary `role="complementary" aria-label="AI-generated summary"`, source list `role="list"`, each source `role="listitem"`
- **Focus order:** Back button → Title → Confidence → AI summary → Source cards in DOM order

### Settings Screen (`/settings`) — NEW
```
┌─────────────────────────────┐
│ safe-area-inset-top          │
├─────────────────────────────┤
│ NavBar (48px)                │
├─────────────────────────────┤
│ pt: 24px                     │
│                              │
│ Settings (28px hero)         │
│                              │
│ ┌──────────────────────────┐ │
│ │ OpenAI API Key            │ │
│ │ (description text)        │ │
│ │                           │ │
│ │ ┌──────────────────── 👁┐ │ │
│ │ │ ••••••••••••XXXX       │ │ │
│ │ └────────────────────────┘ │ │
│ │                           │ │
│ │ [  Save Key  ] [Remove]   │ │
│ │                           │ │
│ │ [ Test Connection ]       │ │
│ │                           │ │
│ │ ● Connected (green)       │ │
│ │   Verified 2h ago         │ │
│ └──────────────────────────┘ │
│                              │
│ (encrypted, stored securely) │
│                              │
│ pb: safe-area-inset-bottom   │
└─────────────────────────────┘
```
- **Max form width:** 480px within 640px content column
- **Input field:** Full-width, 48px height, `--radius-md` corners, `--surface` background, `--border` border. Focus: 2px `--accent` outline offset 2px
- **Show/hide toggle:** 44px eye icon button inside input field (right-aligned)
- **Buttons:** Full-width primary (Save), secondary (Test), ghost (Remove). All 48px height, `--radius-md`
- **Status indicator:** 8px dot + text. Green (--agree) = "Connected", Red (--dismiss) = error message, Muted (--text-ghost) = "Not tested"
- **State machine:**
  ```
  idle (no key) → editing → saving → idle (key saved, show last4)
  idle (has key) → editing (change) | removing → idle (no key)
  idle (has key) → testing → test_success | test_error → idle
  ```
- **No 320px overrides needed** — single-column form adapts naturally

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-26 | Dark-first with amber accent | Intelligence-brief aesthetic; monochromatic-until-interaction builds trust and focus |
| 2026-03-26 | Instrument Serif italic for headlines | Editorial authority without feeling like a generic news app; italic adds hand-set quality |
| 2026-03-26 | No images on discover/briefing cards | Forces content-first reading; removes visual noise; differentiates from every other news app |
| 2026-03-26 | Visible confidence scoring | Builds trust with news-savvy users; teaches attention calibration; unique differentiator |
| 2026-03-26 | High-inertia swipe physics | Cards feel weighty and deliberate, not playful — matches intelligence-brief aesthetic |
| 2026-03-26 | 3-segment top nav instead of bottom tabs | Minimal chrome; saves vertical space on mobile; gestural navigation between screens |
| 2026-03-26 | Mobile viewport specs added | Pixel-precise per-screen layouts, safe areas, device tiers, responsive card heights |
| 2026-03-26 | Settings screen as utility page | Gear icon in NavBar (not a nav segment) — settings is utility, not primary workflow |
| 2026-03-26 | Per-user encrypted API key storage | Fernet encryption in DB, env var fallback, forward-compatible with multi-user |
