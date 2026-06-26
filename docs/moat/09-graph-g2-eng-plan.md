# Wave D Phase 3 — G2: Personalized Entity Overlay (engineering plan)

## NewsLens G2 â€” Personalized Entity Overlay (FINAL, TDD-ready)

### What G2 is (after eng + product review)

G1 shipped the **global** entity backbone (`entities`, `entity_aliases`, `article_entities`) plus pure-SQL "cast strip" (`cluster_entities` at `backend/app/services/entities.py:23`) and "appears in" (`entity_clusters` at `:43`). Wave D Phase A landed auth + RLS: `get_current_user` (`backend/app/services/auth.py:91`) sets the `app.user_id` GUC via `SELECT set_config('app.user_id', :uid, true)` (`auth.py:101`), and four per-user tables (`user_feedback`, `user_preferences`, `user_settings`, `follows`) carry the enforce-when-set policy mirrored in both `backend/app/models.py:381` (`_RLS_TABLES`) and migration `c9d0e1f2a3b4_wave_d_rls`.

**G2 as scoped here is the thin per-user overlay only** â€” the embedding-NN + auto-merge substrate is **deferred** (see "What we are NOT building"). G2 adds:

1. `user_entity_relevance` â€” per-user affinity row, `PRIMARY KEY (user_id, entity_id)`, RLS-scoped by joining `_RLS_TABLES`. Driven by follows (explicit) + reading feedback (implicit), with decay computed at read time.
2. `follows.entity_id` FK â€” persist the link the S7 hook currently only logs (`routes.py:1283-1284`), keeping `uq_follow` live through a nullable add so no follow orphans.
3. **Personalized ranking of the cast strip** (`cluster_entities` only â€” see the eng correction below) â€” an optional `LEFT JOIN user_entity_relevance` reweight so the entities the owner follows / has read rank first. Pure-SQL, byte-identical to G1 when the flag is off.
4. The **production non-superuser DB role** that makes the entire RLS story a live control instead of theater (the single most important eng correction).

### Honest gate note (read first)

docs/moat/05 + 07 gate the overlay on four conditions:

| Gate | Required | Status |
|---|---|---|
| 1. Auth landed | Firebase real `user_id`, RLS live | âœ… LANDED (tasks 19â€“20) â€” but RLS only *enforces* after the prod role lands (S0b) |
| 2. Real user base | ~50â€“100+ WAU | âŒ Single user |
| 3. Surviving multi-hop need | â‰¥15â€“20% recall failures, proven by intent-router logs | âŒ No intent-router logs exist |
| 4. Resolution SLO | >85%, continuously monitored | âŒ Not monitored |

**Only Gate 1 is (partly) met.** The owner directed building G2 now, so this plan builds only the pieces that are **cheap, single-user-valuable, and rework-free at scale**, and defers the rest with explicit re-entry conditions.

### What we ARE building (this phase)
S0 (config + N* one-pager), **S0b (prod non-superuser role â€” eng-mandated, makes RLS real)**, S1 (`user_entity_relevance` + RLS parity), S2 (`follows.entity_id` + persist via the **chip's entity_id**, not string re-resolution), S3 (personalized cast-strip ranking â€” **the visible win**), S4 (feedback â†’ UER + decay-on-read).

### What we are NOT building (deferred, with re-entry conditions) â€” product cut, eng-concurred
- **S5â€“S7: `entities.embedding` + HNSW + backfill + embedding-NN tie-breaker.** Payoff is "fewer duplicate entities," which at single-user volume is the same cosmetic two-chips blemish G1 already accepted. G2's volume pieces (the overlay) add **zero** entities; extraction volume is unchanged from G1. Re-enter when real data shows duplicate entities degrading the cast strip, AND a **co-typed-homonym precision fixture** exists to gate the flag (two MPs, two "Apple" orgs, two Springfields must stay unmerged at `tau_auto`) â€” the generic resolution SLO cannot catch collisions it doesn't enumerate.
- **S8â€“S9: reversible auto-merge + `entity_merge_log` + atomic re-point + unmerge.** The plan's own justification ("the overlay JOIN makes a false merge cost something") **does not hold at N=1**: one reader, so a false merge corrupts that reader's read with or without the overlay. Blast radius only grows at N=many. doc 05 Decision #6 requires auto-merge to ship WITH a continuous SLO monitor + human-in-the-loop; neither exists. Re-enter only after S0b's prod role is live (so a cross-user re-point is actually policy-guarded) AND the homonym fixture gates the merge flag. At single-user the correct answer is G1's: **don't merge, leave two thin chips.**
- Gate 3 (intent-router logs) stays open and is **not** addressed here â€” flagged as the honest blocker on any future graph traversal.

### Architectural invariants (do not violate)

- **Overlay is JOIN/filter only, never a graph-per-user** (05 Decision #1). `entities` / `entity_aliases` / `article_entities` stay **global** (NOT in `_RLS_TABLES`). Only `user_entity_relevance` is RLS-scoped. Relevance never writes back into the shared graph.
- **Reuse the RLS machinery, don't fork it.** Add `"user_entity_relevance"` to `_RLS_TABLES` (`models.py:381`) â†’ it inherits ENABLE + FORCE + the `*_user_isolation` policy via `_install_rls_events()` (`models.py:400`), and the new migration mirrors it exactly like `c9d0e1f2a3b4` (loop `rls_statements("user_entity_relevance")`). The parity test (`test_foundation.py:194`) guards it for free.
- **RLS is only a live control under a non-superuser role.** `test_rls.py:3-6` is explicit: the dev/prod `newslens` role is a superuser (`rolbypassrls`) and `docker-compose.yml` connects as exactly that role, so RLS is **bypassed in production today**. The RLS tests pass only because they `SET ROLE rls_probe`. **S0b provisions the non-superuser app role.** Until S0b lands, every RLS claim is labeled "enforced only under the restricted probe role; production currently bypasses."
- **The explicit `WHERE user_id = current_user_id()` is the PRIMARY control** (`models.py:379`). RLS is defense-in-depth. The cast-strip ranking query is scoped to one cluster's ~12 entities, so the planner hash-joins a tiny UER set â€” `ix_uer_user_score` is **not** range-scanned here; it is justified by a future global-ranking query, not this one (do not claim index-ordered ranking on the cast strip).
- **SET LOCAL, never SET** â€” already done in `auth.py:101`. The overlay inherits the asyncpg pooled-connection isolation fix for free.
- **Cache hash must widen to user scope.** The G2 breadcrumb (`entities.py:6-8`) warns any personalized lens output must include `user_id + entity_ids + content version + persona/depth` in its `_source_hash`. The personalized reads here are **uncached pure-SQL**, so the trap doesn't bite â€” but S3's ranking key is the contract for the first personalized lens that caches.

### Slice ordering (early visible per-user win first)

**S0 â†’ S0b â†’ S1 â†’ S2 â†’ S3 delivers the owner's followed entities ranking first in the cast strip by the visible win**, before any further work. Honest ordering nit: **S1 + S2 alone produce zero visible change** â€” UER's only consumer is S3's ranking. S2 ("following writes a real entity_id + relevance row") is plumbing; the user sees nothing until S3. The win is S3-gated.

| # | Slice | Outcome |
|---|---|---|
| S0 | Config knobs + N* economics one-pager | Gate-2 number on paper; no code risk |
| S0b | Prod non-superuser DB role + startup assertion | RLS becomes a real control (eng-mandated) |
| S1 | `user_entity_relevance` + RLS (parity) | Overlay substrate exists, isolated |
| S2 | `follows.entity_id` + persist chip's entity_id + UER follow row | Following an entity writes a real `entity_id` (kind-unambiguous) + a relevance row |
| **S3** | **Personalized ranking in `cluster_entities`** | **Owner's followed entities rank first â€” the visible win** |
| S4 | Feedback â†’ UER + decay-on-read | Read/save behavior feeds the same ranking |

### Migration chain (linear, explicit â€” eng correction)
Current head is `d0e1f2a3b4c5` (G1 backbone). Chain each new migration onto the prior to avoid multiple-heads:
`e1f2a3b4c5d6` (S1, down_revision `d0e1f2a3b4c5`) â†’ `f0a1b2c3d4e5` (S2, down_revision `e1f2a3b4c5d6`). State the down_revision as a slice acceptance criterion so each slice rebases onto the prior. (S0b is role/env config + a migration-time `op.execute` guard only if a DB object is needed; it carries no schema migration of its own unless it adds the role via SQL â€” if so, sequence it `e1f2a3b4c5d6`'s parent.)

### Per-slice TDD detail

**S0 â€” Config + economics (no schema).** Add to `backend/app/config.py` (mirroring the `graph_*` block at lines 67â€“75): `uer_enabled: bool = False`, `uer_half_life_days: float = 21.0`, `uer_follow_weight: float = 1.0`, `uer_rank_alpha: float = 0.6` (global salience), `uer_rank_beta: float = 0.4` (decayed user relevance). **Flag the decay/weight constants as assumption-grade hypotheses** â€” no single-user data can tune them; do not over-index on the values. Ship the N* one-pager: N* = `extraction_cost_per_day / vector_baseline_cost_per_user_per_day` from real ingest/token numbers (Gate-2 deliverable, no code). *Red:* `test_g2_config_defaults` asserts every knob exists with its safe-off default. *Green:* add the fields.

**S0b â€” Production non-superuser DB role + startup assertion (eng-mandated; the single most important missing piece).** *Red:* `test_rls_active_under_app_role` (integration) â€” provision/connect as a NOBYPASSRLS role and assert `current_setting('is_superuser') = 'off'` AND that a cross-user UER select is filtered **without** `SET ROLE` (proving the connection role itself enforces, not just the probe). *Green:* document + script `CREATE ROLE newslens_app NOLOGIN; GRANT ... ; ALTER ROLE newslens_app NOBYPASSRLS;` (or `LOGIN` with its own password), switch `DATABASE_URL` to it, and add a `main.py` lifespan startup assertion that logs a loud warning (or refuses to start when `AUTH_REQUIRED=true`) if `is_superuser='on'`. Until this lands, the per-user **write** overlay is unguarded in prod â€” the assertion makes the gap visible.

**S1 â€” `user_entity_relevance` + RLS.** *Red:* `test_uer_rls_isolation` (under `SET ROLE rls_probe`, mirroring `test_rls.py`) â€” with the GUC set to user A, B's UER rows are invisible; GUC unset â†’ permissive (background ranking sees all). `test_alembic_baseline_matches_models` (`test_foundation.py:194`) must stay green (parity). *Green:* add the `UserEntityRelevance` ORM model (`backend/app/models.py`, columns below); append `"user_entity_relevance"` to `_RLS_TABLES` (`models.py:381`); migration `e1f2a3b4c5d6_g2_user_entity_relevance` (down_revision `d0e1f2a3b4c5`) creates the table + `ix_uer_user_score (user_id, score DESC)` and loops `rls_statements("user_entity_relevance")` exactly like `c9d0e1f2a3b4`. **Update the integration conftest** (`backend/tests/integration/conftest.py:36`) so the new table is FORCE-RLS'd under the probe role if the probe-grant logic needs it (eng correction: keep test schema matched to the migration).

**S2 â€” `follows.entity_id` + persist (the chip's id, NOT string re-resolution).** Eng correction: `resolve_existing` (`entities.py:58`) is **kind-blind** (matches `name_norm` alone), so following the surface form "Jordan" could resolve personâ†’place, and S3 would then rank the wrong entity. **Fix = option (b): the UI already knows the entity_id** (`EntityChips.tsx` has `e.id` at line 60). *Red:* `test_entity_follow_persists_entity_id` â€” POST `/follows` with `kind=entity` and an `entity_id` sets `follow.entity_id` and writes a `user_entity_relevance` row with `source='follow'`, `engagement_raw=uer_follow_weight`, `last_event_at=now`; idempotent re-follow is a no-op. *Green:* (1) add optional `entity_id: int | None` to `FollowCreate` (`backend/app/schemas.py:312`); (2) add nullable `entity_id` FK + `ix_follows_entity` to `Follow` (`models.py:273`), migration `f0a1b2c3d4e5_g2_follow_entity_id` (down_revision `e1f2a3b4c5d6`) adds the **nullable** column keeping `uq_follow` live (no orphan window); (3) change `routes.py:1278-1284` from log-only to persist `body.entity_id` (when present) and upsert the UER row â€” skip `resolve_existing` entirely when the id is supplied; fall back to the existing log-only resolution when it isn't (documented cross-kind blemish for the string path). (4) Frontend: wire the chip's `e.id` into the follow call (extend `addFollow` in `frontend/src/lib/api.ts:488` to accept an optional `entityId`).

**S3 â€” Personalized cast-strip ranking (the visible win).** Eng corrections applied: (a) **scope to `cluster_entities` only** â€” `entity_clusters` (`entities.py:43`) orders by `StoryCluster.created_at.desc()` and has **no per-row salience**, so the Î±/Î² formula is undefined there; drop the personalization claim for the "appears in" rail (a real signal â€” e.g. boosting clusters that contain *other* followed entities â€” is a separate future design, not a copy-paste). (b) **Handle the GROUP BY** â€” `cluster_entities` groups by `Entity.id, canonical_name, kind` with `func.max(salience)`; the `LEFT JOIN user_entity_relevance` columns (`engagement_raw`, `last_event_at`) must be added to the GROUP BY (one UER row per entity by PK, so functionally determined, but Postgres still requires it) or wrapped in `max()`. *Red:* `test_cluster_entities_personalized` â€” two entities of equal global salience, the one with a UER row ranks first; `test_cluster_entities_identical_when_disabled` â€” with `uer_enabled=False`, output is byte-identical to G1 (regression guard). *Green:* extend `cluster_entities` with an optional `user_id` param â†’ `LEFT JOIN user_entity_relevance ON entity_id AND user_id = :uid`, `ORDER BY (alpha*max_salience + beta*COALESCE(decayed_relevance,0)) DESC`; pass `current_user_id()` from the endpoint (`routes.py:1218` â€” already `Depends(get_current_user)`, zero new auth wiring). Do **not** claim `ix_uer_user_score` serves this ORDER BY (cluster-scoped hash join, ~12 entities).

**S4 â€” Feedback â†’ UER + decay-on-read.** *Red:* `test_feedback_updates_relevance` â€” a `save`/`read` on an article linked to entity E bumps `engagement_raw` + `last_event_at` for (user, E); `test_relevance_decay_on_read` â€” an old `engagement_raw` contributes less than a fresh one via `exp(-ln2 * age_days / half_life)`. *Green:* on feedback write (`routes.py:343` `/feedback`), upsert UER rows for the article's linked entities (`article_entities` lookup); compute decayed `effective` **at read time** inside the S3 ranking SQL (materialize-on-write, decay-on-read â€” no cron). Eng correction: because ranking recomputes decay from `engagement_raw + last_event_at` at read time, the materialized `score` column is **not** the ordering key â€” `ix_uer_user_score` serves only the `WHERE user_id=` filter; the `DESC` is decorative. Either keep `score` as an optional write-time cache OR drop it; do not claim index-ordered ranking.

### Validation per slice
`cd backend && pytest -x` (Docker, per Windows-ARM greenlet note), `ruff check .`, and after S1/S2 the full `pytest tests/integration/test_foundation.py` to confirm parity. Frontend: the cast strip (`EntityChips.tsx`) already consumes `/clusters/{id}/entities`; S3 changes ordering only, so `cd frontend && npm run build` (`--webpack`) + `npx vitest run` + `npm run lint:copy` confirm no contract break. S0b is validated by the new integration test under the non-superuser role and the startup assertion.

## Schema tables

### `user_entity_relevance (NEW, RLS-scoped â€” add to _RLS_TABLES)`
Per-user affinity overlay on the global entity graph. The ONLY new RLS-scoped table. Drives personalized cast-strip ranking (S3). JOIN/filter only â€” never a graph-per-user; relevance never writes back into the shared graph.

- `user_id INT NOT NULL FK users.id â€” RLS-scoped via current_setting('app.user_id')`
- `entity_id INT NOT NULL FK entities.id (global table; ON DELETE CASCADE OK â€” no merge in this phase, so no re-point-before-delete ordering hazard)`
- `PRIMARY KEY (user_id, entity_id) â€” at most one row per user/entity, so the S3 LEFT JOIN is functionally determined`
- `source VARCHAR(16) NOT NULL â€” 'follow' | 'feedback'`
- `engagement_raw FLOAT NOT NULL DEFAULT 0 â€” accumulated weight (follow_weight on follow; increments on save/read)`
- `last_event_at TIMESTAMPTZ NOT NULL â€” drives exp(-ln2*age_days/half_life) decay computed AT READ TIME`
- `score FLOAT NULL â€” OPTIONAL write-time cache; NOT the ranking key (ranking recomputes decay at read time). Drop if it adds confusion.`
- `INDEX ix_uer_user_score (user_id, score DESC) â€” serves the WHERE user_id= filter only; does NOT serve the cast-strip ORDER BY (decay is a runtime expression)`

### `follows (EXISTING â€” add nullable entity_id)`
Persist the entity link the G1 S7 hook currently only logs (routes.py:1283). Nullable add keeps uq_follow(user_id,kind,value) live â€” no orphan window. entity_id comes from the tapped chip (EntityChips.tsx e.id), NOT from kind-blind string re-resolution.

- `entity_id INT NULL FK entities.id â€” NEW, nullable (backfill-safe)`
- `INDEX ix_follows_entity (entity_id) â€” NEW`
- `(existing) user_id, kind, value, created_at, uq_follow(user_id,kind,value) â€” unchanged`

### `_RLS_TABLES tuple (models.py:381 â€” EXTEND)`
Append 'user_entity_relevance' so it inherits ENABLE+FORCE RLS + the *_user_isolation enforce-when-set policy via _install_rls_events(); the new migration mirrors it exactly like c9d0e1f2a3b4. entities/entity_aliases/article_entities stay OUT (global).

- `('user_feedback', 'user_preferences', 'user_settings', 'follows', 'user_entity_relevance')`

### `newslens_app role (NEW â€” S0b, not a table)`
Production non-superuser DB role so RLS is a live control instead of theater (test_rls.py:3-6 + docker-compose connect as a superuser today, bypassing RLS). Without this the per-user WRITE overlay is unguarded in prod.

- `CREATE ROLE newslens_app NOBYPASSRLS with GRANTs on app tables`
- `DATABASE_URL switched to this role`
- `main.py lifespan startup assertion: current_setting('is_superuser')='off'`

## TDD slices

### S0 — Config knobs + N* economics one-pager (no schema)
- **RED:** test_g2_config_defaults â€” asserts uer_enabled, uer_half_life_days, uer_follow_weight, uer_rank_alpha, uer_rank_beta all exist on Settings with their safe-off / hypothesis-grade defaults.
- **GREEN:** Add the five uer_* fields to Settings mirroring the graph_* block (config.py:67-75); uer_enabled defaults False. Flag the decay/weight constants as assumption-grade. Write the N* one-pager (extraction_cost_per_day / vector_baseline_cost_per_user_per_day) from real ingest numbers â€” Gate-2 deliverable, no code.
- **Files:** backend/app/config.py, backend/tests/test_settings.py, docs/moat/g2-economics-onepager.md

### S0b — Production non-superuser DB role + startup RLS assertion (eng-mandated)
- **RED:** test_rls_active_under_app_role (integration) â€” connect as a NOBYPASSRLS role, assert current_setting('is_superuser')='off' AND a cross-user UER/feedback select is filtered WITHOUT SET ROLE (the connection role itself enforces).
- **GREEN:** Script CREATE ROLE newslens_app NOBYPASSRLS + GRANTs; switch DATABASE_URL to it; add a main.py lifespan assertion that logs a loud warning (or refuses startup when AUTH_REQUIRED=true) if is_superuser='on'. Document the prod cutover in CLAUDE.md / docker-compose.
- **Files:** backend/app/main.py, backend/app/database.py, docker-compose.yml, backend/tests/integration/test_rls.py, CLAUDE.md

### S1 — user_entity_relevance table + RLS (parity-guarded)
- **RED:** test_uer_rls_isolation (under SET ROLE rls_probe, mirroring test_rls.py) â€” GUC=userA hides userB's rows; GUC unset â†’ permissive. test_alembic_baseline_matches_models stays green.
- **GREEN:** Add UserEntityRelevance ORM model (PK user_id,entity_id; source, engagement_raw, last_event_at, optional score; ix_uer_user_score). Append 'user_entity_relevance' to _RLS_TABLES (models.py:381). Migration e1f2a3b4c5d6_g2_user_entity_relevance (down_revision d0e1f2a3b4c5) creates table + index + loops rls_statements(...). Update integration conftest so the new table is created/FORCE-RLS'd to match the migration.
- **Files:** backend/app/models.py, backend/migrations/versions/e1f2a3b4c5d6_g2_user_entity_relevance.py, backend/tests/integration/test_rls.py, backend/tests/integration/conftest.py, backend/tests/integration/test_foundation.py

### S2 — follows.entity_id FK + persist the chip's entity_id + UER follow row
- **RED:** test_entity_follow_persists_entity_id â€” POST /follows kind=entity with entity_id sets follow.entity_id AND writes a user_entity_relevance row (source='follow', engagement_raw=uer_follow_weight, last_event_at=now); idempotent re-follow is a no-op. Frontend: FollowButton/EntityChips passes e.id.
- **GREEN:** Add optional entity_id to FollowCreate (schemas.py:312). Add nullable entity_id FK + ix_follows_entity to Follow (models.py:273); migration f0a1b2c3d4e5 (down_revision e1f2a3b4c5d6) adds the nullable column keeping uq_follow live. Change routes.py:1278-1284 to persist body.entity_id + upsert the UER row, skipping kind-blind resolve_existing when the id is supplied (string path stays log-only, documented blemish). Wire e.id through addFollow (api.ts:488) + EntityChips.
- **Files:** backend/app/models.py, backend/app/schemas.py, backend/app/api/routes.py, backend/migrations/versions/f0a1b2c3d4e5_g2_follow_entity_id.py, frontend/src/lib/api.ts, frontend/src/components/ui/EntityChips.tsx, backend/tests/test_api.py

### S3 — Personalized cast-strip ranking (the visible win)
- **RED:** test_cluster_entities_personalized â€” two entities of equal global salience, the followed one (UER row present) ranks first. test_cluster_entities_identical_when_disabled â€” uer_enabled=False â‡’ byte-identical to G1.
- **GREEN:** Extend cluster_entities (entities.py:23) with optional user_id â†’ LEFT JOIN user_entity_relevance ON entity_id AND user_id=:uid; add uer columns to the GROUP BY (or max()); ORDER BY (alpha*max_salience + beta*COALESCE(decayed_relevance,0)) DESC. Pass current_user_id() from routes.py:1218 (already Depends(get_current_user)). Do NOT personalize entity_clusters (no per-row salience) and do NOT claim ix_uer_user_score serves this ORDER BY.
- **Files:** backend/app/services/entities.py, backend/app/api/routes.py, backend/tests/integration/test_entities.py

### S4 — Feedback â†’ UER write + decay-on-read
- **RED:** test_feedback_updates_relevance â€” a save/read on an article linked to entity E bumps engagement_raw + last_event_at for (user,E). test_relevance_decay_on_read â€” an old engagement_raw contributes less than a fresh one via exp(-ln2*age_days/half_life).
- **GREEN:** On /feedback write (routes.py:343), upsert UER rows for the article's linked entities (via article_entities). Compute decayed effective at read time in the S3 ranking SQL (materialize-on-write, decay-on-read, no cron). Keep score as optional write-time cache OR drop it; do not claim index-ordered ranking since the real ordering key is a runtime decay expression.
- **Files:** backend/app/api/routes.py, backend/app/services/entities.py, backend/tests/integration/test_entities.py, backend/tests/test_api.py

## Risks
- RLS is BYPASSED in production today: the newslens role is a superuser (rolbypassrls, test_rls.py:3-6) and docker-compose connects as it, so until S0b lands the per-user WRITE overlay (UER upserts on follow/feedback) has zero policy guard. S0b's startup assertion is what surfaces the gap; the explicit WHERE user_id=current_user_id() filter remains the primary always-on control regardless.
- Follow resolution is kind-blind in the string path: resolve_existing (entities.py:58) matches name_norm alone, so following the text 'Jordan' could resolve personâ†’place and S3 would rank the wrong entity. Mitigated by persisting the chip's entity_id (option b); the remaining string-path follow stays log-only and is a documented accepted blemish, NOT wired into UER.
- Decay/weight constants (half_life=21d, alpha=0.6/beta=0.4) are assumption-grade â€” no single-user data can tune them. Shipped as config knobs; treat as hypotheses, not validated values.
- Index claim trap: ix_uer_user_score does NOT serve the cast-strip ORDER BY â€” the ranking recomputes decay at read time (a runtime expression) and the query is cluster-scoped (~12 entities, hash join). The index serves only the WHERE user_id= filter and a future global-ranking query. Do not assert index-ordered ranking on the cast strip.
- GROUP BY correctness: cluster_entities aggregates with func.max(salience); the UER columns must be added to the GROUP BY (or wrapped in max()) or Postgres errors. PK (user_id,entity_id) makes them functionally determined but the SQL still requires it.
- Deferred S5â€“S9 means duplicate entities remain possible (G1's accepted two-thin-chips blemish). Re-entry requires a co-typed-homonym precision fixture (tau_auto=0.08 + kind-block does NOT separate two MPs / two 'Apple' orgs / two Springfields) AND the prod non-superuser role, so a future cross-user merge re-point is actually policy-guarded. Auto-merge on a shared graph with RLS bypassed and no precision gate is the one place 'rework-free at scale' would be false â€” hence the defer.
- Cache breadcrumb (entities.py:6-8) is dormant only because the personalized reads here are uncached pure-SQL. The first personalized lens that caches MUST widen its _source_hash to include user_id + entity_ids + content version + persona/depth, or it serves stale/cross-tenant answers. S3's ranking key is that contract.
- Migration multi-heads risk: current head is d0e1f2a3b4c5. The two new migrations must chain linearly (e1f2a3b4c5d6â†’d0e1f2a3b4c5, f0a1b2c3d4e5â†’e1f2a3b4c5d6); a copy-pasted down_revision would create branching heads and break test_foundation's command.upgrade(cfg,'head').

_Generated by the graph-g2-eng-plan workflow (8 agents). Embedding-NN + auto-merge deliberately deferred (re-entry conditions in the plan)._

