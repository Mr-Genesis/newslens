# Wave C — Engineering Plan: The Habit Loop (Digest · Alerts · Follows)

> Parent: [`00-PLAN.md`](00-PLAN.md). Follows Wave B. Goal: the **return trigger** — bring the
> reader back to something worth returning to (only valuable once A+B exist).
> Reviewed: CEO (scope set by 00-PLAN), Eng, Design (findings inline).

## Scope
- **C1 AI morning digest** — "3 things that moved in your world overnight, 90-sec read."
- **C2 Breaking alerts** — surface high personal-relevance new clusters (reuses Wave A's relevance score).
- **C3 Standing Follows** — topic / entity / saved-search → persistent feed rail + new-cluster indicator.

## Hard constraint (CEO/eng flag)
Push notifications (FCM) and multi-user auth are **parked** ([`docs/enhancement/FIREBASE-DEFERRED.md`](../enhancement/FIREBASE-DEFERRED.md)).
So Wave C delivers the return-trigger **in-app** (a "While you were away" surface + unread/new
indicators), NOT OS push. This is the honest scope for a single-user, no-auth app today; the
generation + ranking work done here is exactly what a future FCM push would send, so it's not wasted.

## What already exists (reuse)
- APScheduler in `main.py` (7 jobs) — add a digest-compose job (or compute lazily).
- Wave A impact relevance `score` — the ranking signal for digest + alerts (no new scoring).
- `user_preferences` (topic weights) — topic follows already exist here; extend, don't duplicate.
- Clustering pipeline — "new cluster since last visit" is a timestamp query, not new infra.
- Briefing screen — the digest is a card/section on Today, not a new screen.

## Data model
- **`follows`** (new, migration): `id, user_id, kind ('topic'|'entity'|'saved_search'), value, created_at`,
  `UNIQUE(user_id, kind, value)`. Topic follows may mirror to `user_preferences` for feed weighting.
- **Digest:** compute-on-open (lazy) keyed by `(user, date)` cached on a light `daily_digest` row OR
  reuse the cluster cache pattern — no per-story LLM calls beyond the already-cached impact headlines.
- **"Last seen":** a `users.last_seen_at` column to scope "while you were away" + new-cluster counts.

## Eng review findings (applied)
- **E1 No push yet:** all "alerts" are in-app indicators (new-cluster badge on a follow rail, unread
  count). Don't build a delivery channel that needs FCM/auth. Flag clearly in the UI ("in-app only").
- **E2 Digest cost:** build the digest from ALREADY-cached impact headlines + summaries (no fresh LLM
  fan-out); only the 90-sec framing line is a single LLM call, cached per (user, date). Bounded.
- **E3 Follows → feed:** topic follows feed the existing explore/exploit weights; entity/saved-search
  follows run the existing `/search` (semantic+keyword) on a schedule/open to find new clusters.
- **E4 Idempotency/edge:** digest job runs once/day per user (guard double-runs); empty state (nothing
  moved) is a first-class "you're all caught up" message, not a blank.
- **E5 Tests:** unit — follow CRUD + uniqueness, digest ranking by relevance, empty-digest path;
  integration — follow → rail surfaces new clusters, digest composes from cached data with 0 extra LLM
  calls (assert generate count), last_seen gating. Extend fake_llm only for the single framing line.

## Design review findings (applied)
- **D1 "While you were away"** card at the top of Today: ≤3 items, each = headline + the WIIFM
  one-liner (reuse) + relevance chip; tap → Deep Dive. Quiet, in-brand (no badges-spam).
- **D2 Follow management:** a simple followed-list (topics/entities/searches) with one-tap unfollow;
  "follow this" affordance from search results + story topics.
- **D3 States:** digest — loading / empty ("all caught up") / ready; follow rail — empty (suggest
  follows) / new-since-last-visit count / no-new. Alerts — subtle accent dot, never a red badge storm.
- **D4 a11y + brand:** indicators are text+icon, not color-only; amber used sparingly; no streak-style
  pressure (consistent with the quiet-authority brand — note: the *trivia* streak stays per owner call,
  but the digest/alerts must not become engagement-bait).

## Decisions (resolved 2026-06-24)
1. **Delivery = in-app "while you were away" now** (no auth/FCM). The generation/ranking is reusable by a future FCM push.
2. **Digest = lazy compute on first open per day**, cached per (user, date). No scheduled job in v1.
3. **Follows = a unified `follows` table** for topic/entity/saved_search (topics may mirror to `user_preferences` for feed weighting).

## NOT in scope
- OS push notifications / FCM (parked, needs auth). Multi-user fan-out. GraphRAG (Wave D).
- Email digest (no mail infra; personal project).

## Checklist (ordered)
- [ ] Migration: `follows` table + `users.last_seen_at`
- [ ] Follow CRUD endpoints (`GET/POST/DELETE /follows`) + "follow this" UI from search/story
- [ ] Follow rails on the feed + new-since-last-visit count
- [ ] Digest compose (lazy, from cached impact/summaries; one framing LLM call cached per user/date) + "While you were away" card
- [ ] In-app new-cluster indicators (no push)
- [ ] Tests: unit (follow CRUD/uniqueness, digest ranking + empty, 0-extra-LLM assertion) + integration (follow→rail, last_seen gating) + frontend (digest card states)
- [ ] Validate: Docker pytest + `npm run build` + vitest + lint:copy
