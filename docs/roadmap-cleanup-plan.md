# Roadmap Cleanup — Plan (7 features)

Grounded in a 7-way parallel design pass over the current code. Each feature is broken into
tracer-bullet vertical slices for a TDD build. Recommended decisions are **adopted as defaults**
below (from the design pass); the genuinely product-shaping ones are flagged **DECISION**.

---

## 1. #82 — Feed filter-chip UI ("All · News · Research · Experts") — effort S, frontend

**State:** `GET /feed?source_type=` + `getFeed(sourceType)` already exist and are correct; nothing
renders them (home = briefing). **Approach:** a NEW static `/feed` route (Capacitor-safe; no dynamic
segment) rather than overloading the briefing's category-chip row (different data shape + filter axis).
Reuse `Chip.tsx`, `SourceTierBadge`, and the `saved/page.tsx` state machine. The feed returns
`Article` (not `BriefingStory`), so a small new `FeedArticleCard` renders it.

- **S1** Feed screen skeleton: four chips (All/News/Research/Experts → all/news/research/expert),
  wired to `getFeed(1,20,undefined,activeType)`, loading/empty/error states.
- **S2** `FeedArticleCard` — title → `storyHref(cluster_id)` or external `article.url`; source name +
  `relativeTime`; `SourceTierBadge` for research/expert (news unbadged). List keyed to the active fetch.
- **S3** Nav entry → an icon-link in the top `NavBar` right cluster (next to Search). **DECISION:**
  top-NavBar icon (keeps the 5-tab bottom bar intact) vs a 6th bottom tab. Default: top-NavBar icon.

Deferred: pagination (page-1 only for the tracer); topic context starts unfiltered.

## 2. Per-specialty PubMed precision — effort S, backend

**State:** `pubmed.py` tags every ingested article `audience=["medicine"]`, so every doctor sees every
specialty. **Approach — Option B (recommended):** keep the broad `medicine` gate (a generalist must
still see content) and add a **per-specialty relevance boost**, not narrow gating (which would blank
out a "Doctor (MBBS)"). This preserves the "generous gating" invariant.

- **S1** Tag each PubMed specialty source with its specialty (additive `credibility_meta.specialty`
  or an extra audience tag) — gating-neutral.
- **S2** `specialty_tags_for_profession()` (keyword, from `_PROFESSION_TERMS`) + a bounded ranking
  boost (×1.25) in the feed blend when the source's specialty matches the user's — stacks safely
  inside the existing `[0.9,1.1]`-style bound so it can't drown breaking news.
- **S3 (deferred)** "For your field" filtered rail — explicit-intent power-user surface; the boost
  already delivers ~80% of the value.

**DECISION:** ship the ranking boost (S1+S2) and **defer the rail (S3)**. Default: yes, defer.

## 3. "Verified spares" — 9 held-back expert sources — effort S, data

**State:** the plan's §3.2 lists 9 curated experts held back (Chartbook 90, Silver Bulletin 81,
Lenny's 73, ChinaTalk 66, Volts 64, The Diff 61, India Uncut 60, Kyla's 57, Strange Loop Canon 56).

- **S1** Re-verify each feed live (`curl`, HTTP 200 + XML/Atom + `<title>` identity) — **blocking; feeds
  rot (~30-50% quarterly attrition per the plan). Drop any that fail (e.g. if natesilver.net/feed 404s).**
- **S2** Append the verified survivors to `sources.json` (source_type=expert, the plan's scores,
  audience tags that `tags_for_profession` can actually emit, `reviewed_by:"seed"`, paywalled Substacks
  `is_paywalled:true`).
- **S3** A `sources.json` shape/credibility guard test (every expert has a score 0-100 + rationale).

**DECISION:** accept the plan's model-estimate scores as the seed values; seed all verified survivors.

## 4. `GET /events` SSE stream — effort M, fullstack

**State:** `sse-starlette` is in requirements; the fetch/cluster scheduler jobs are the event sources.
**Approach:** a tiny in-process pub/sub (`app/services/events.py`) — a singleton hub with
`publish(type,data)` + an async-generator `subscribe()` over a bounded, drop-oldest `asyncio.Queue`.

- **S1** Event hub + scheduler publish points (`fetch_all_rss` → `feed_refresh {new_articles:N}`,
  `run_clustering` → `new_cluster`).
- **S2** `GET /events` SSE endpoint. **DECISION:** v1 is an **UNAUTHENTICATED global signal channel**
  (matches single-user reality; no token in URL; simplest/safest) — carries only ids/counts, never
  per-user data. Default: unauthenticated global channel.
- **S3** Frontend `EventSource` client → live-refresh the `WhileAwayCard` (smallest consumer).

Note: the in-process hub reaches only clients on the same uvicorn worker — fine for the single-process
deploy; documented as a multi-worker caveat.

## 5. `GET /admin/breadth` — effort S, backend

Auth-gated read-only metrics endpoint below the admin-sources block. Aggregate SQL, no N+1.

- **S1** Source-diversity counts: by `source_type`, by `region`, gated-tier share (of sources **and** of
  articles).
- **S2** Articles-per-source (top-N=20 leaderboard + zero-article count) + topic coverage
  (articles per topic).
- **S3** Stale sources (no article in N days). Staleness clock = `max(Article.fetched_at)` (always
  present); window = `settings.breadth_stale_days=30` (`?days=` overridable).

## 6. Discover "tension lines" — effort M, backend

**State:** `DiscoverCardOut.tension_line` falls back to the article title. **Approach:** a tension-line
lens **cached on `cluster.extra_json`**, computed by a **backfill job** (mirrors summaries/entities) —
NOT on-demand (the deck fetches ~25 cards/request). Deck reads are cache-only with title fallback.

- **S1** Tension-line lens: LLM generates one ≤~90-char conflict line (who-vs-what + stakes), cached on
  `extra_json` keyed on the cluster source_hash; `force_platform_key=True`; graceful `LLMUnavailable`.
- **S2** Backfill job in APScheduler (on-change via source_hash, gated by `tension_lines_enabled=True`,
  dedicated `tension_batch_size`/`tension_interval_minutes`).
- **S3** Deck serves the cached tension line, falling back to the title when absent.

## 7. Pull-to-refresh (spec-align) + landscape — effort S, frontend

**State:** pull-to-refresh **already ships** (THRESHOLD=70, 0.5/cap-90 curve) — this **aligns it to the
design-system spec** (60px, 0.4 curve, cap 80) and makes its math unit-testable. Landscape is new.

- **S1** Align pull-to-refresh to the spec numbers; extract the resistance math into a pure, unit-tested
  helper; honor `prefers-reduced-motion`.
- **S2** Percentage-based swipe thresholds on `DiscoverCard` (40% width / 25% height) via props passed
  from `discover/page.tsx` (keeps the card pure + testable) rather than self-measuring.
- **S3** Landscape card-stack height `min(360px,60vh)` via a `globals.css` `(orientation: landscape)`
  block on a stable stack-container class; sticky nav preserved.

---

## Build order & dependencies

Independent features can proceed in any order. Within a feature, slices are mostly linear (S2 blocked by
S1). Cross-feature: none hard-block, but #82 S2 and #6 both touch card rendering — sequence to avoid
churn. Suggested order: 3 (data) → 5 (admin) → 2 (pubmed) → 6 (tension) → 4 (SSE) → 1 (feed UI) →
7 (pull/landscape), backend-heavy first, frontend last.
