# Wave D Phase 3 — Multi-User GraphRAG Knowledge Graph: Scope

> The INTEREST_GRAPH_SPEC + KNOWLEDGE_DEPTH_ENGINE the handover named but never wrote — scoped now
> that **multiple users** are planned. Builds on [`04-wave-d-eng-plan.md`](04-wave-d-eng-plan.md)
> (Phases 1–2 are the unconditional foundation). Researched + designed + adversarially timing-checked.
>
> **Verdict in one line: the scope is right; multi-user flips the economics, but it does NOT move the
> build forward. Build the graph LATER, gated. The present-tense answer is unchanged: Wave D Phase 1,
> frameworks-first, no graph.**

## Why multi-user changes the verdict (and what it doesn't)

Wave D rejected a full GraphRAG **for a single user** on one axis: the one-time entity-extraction/index
cost couldn't amortize, and vector neighbour recall already bought ~80% of the depth. **Multi-user flips
exactly that axis** — extraction is **content cost, not user cost**: it runs once per article/cluster and
is queried by *every* user, so **cost-per-user falls as users grow**. That removes the *economic* veto.

It removes **only** that veto. Three vetoes remain fully intact (all verified against the code today):
- **Foundation:** bodies are still truncated (`gdelt.py:122` `extracted[:300]`, `fetcher.py:254` `summary[:300]`; no body column); `services/retrieval.py` and `cluster_edges` don't exist. A graph built now would reason over **headlines**.
- **Quality:** entity resolution must clear a gate, and on a *shared* graph a bad merge poisons every user.
- **Auth:** every request is `DEFAULT_USER_ID = 1` today; the per-user overlay is fictional until Firebase lands.

> "I'll have multiple users" is **intent, not traction.** Multi-user makes the graph *worth building when
> the gates pass* — not *buildable now*.

## Architecture — shared global graph + thin per-user overlay

This maps almost perfectly onto the **existing** schema (content tables already carry no `user_id`; user
tables already do), and rides on Wave D Phases 1–2 — the graph is one more recall source inside
`build_context()`, never a replacement.

| | GLOBAL (shared, computed once, no `user_id`) | PER-USER OVERLAY (`user_id`-scoped, RLS) |
|---|---|---|
| Data | entities, aliases, events, edges, `article_entities`, embeddings, extraction | relevance of a global entity/event to a persona; watchlist/follows; ask history; overlay edges ("user follows X") |
| Cost | fixed; **/N falls with users** | scales with N (keep tiny) |
| Privacy | none (public facts) | **must never cross tenants** |
| Maps to | articles / story_clusters / cluster_edges (already global) | user_feedback / user_preferences / follows / user_settings (already user-scoped) |

**Personalization is an overlay filter (a JOIN), never a graph-per-user.** A graph-per-user destroys the
amortization that is the entire economic case for building under multi-user.

## Schema (additive)

- **Global:** `entities(id, canonical_name, kind, embedding, first/last_seen, mention_count)`; `entity_aliases(entity_id, alias)`; `article_entities(article_id, entity_id, salience, confidence)`; `events(id, cluster_id FK UNIQUE, occurred_at, embedding)` (a cluster ≈ an event); `entity_edges(src, dst, relation, event_id, observed_at, weight)` (time-stamped); **`entity_merge_log`** (provenance → merges are reversible). Entity-LIGHT (salience filter; never every noun).
- **Overlay (RLS):** `user_entity_relevance`, `user_event_relevance`; migrate `Follow.value` (today free-text `String(255)`) → a stable `entity_id` FK; user-scope ask history. `User.firebase_uid` (unique, nullable during migration).
- Indexes: every overlay table leads with `user_id`; `entity_edges(src)`, `(dst)` for CTE fan-out; `article_entities(entity_id)` reverse lookup; `events.embedding` ivfflat/hnsw reusing the Article config.

## Extraction — global, amortized, incremental

A per-article/cluster LLM pass (salient-entity NER + alias normalization + edge inference + temporal
stamps) hooked into the **existing 10-min clustering job**, **LightRAG-style merge-on-ingest** — never a
Microsoft-GraphRAG **batch rebuild** (~610k tokens/query, dismantles structure on every add — fatal for a
continuous feed). Resolution: auto-merge **only at 0.90–0.95+ confidence**; the uncertainty band → a
human-in-the-loop queue; every merge logged with provenance (reversible); merge/split **re-points overlay
FKs** so no follow is orphaned. (Cost reality, carried from the Wave D review: GDELT `mode=artlist`
returns **no** free GKG entities, and no cluster centroids are stored — extraction is real new cost, just
amortized.)

## Retrieval — hybrid, per-user-scoped, intent-routed

Layered into `build_context()`: **(1) intent routing** — simple single-story questions **skip the graph**
(stay focal + pgvector neighbour recall, the Phase-1 path); only relational/multi-hop questions enter the
graph. **(2) graph recall** — a depth-**1–2** recursive CTE over edges returns the neighbourhood
(microseconds; cap at 2 hops — `0.85^n` error compounding makes 3+ untrustworthy on a shared graph).
**(3) per-user scoping** — filter/reweight candidates by JOINing the overlay under RLS. **(4) pgvector
rerank** — vector ranks the graph-recalled candidates (the 2-hop hit-rate 0.28→0.83 unlock). **(5) budget**
— graph keywords ~100 tokens (LightRAG), bodies budgeted per the depth ladder. **Cache:** `_source_hash`
must cover retrieved ids + content version + persona/depth **+ user scope**, or the JSONB cache serves one
user's stale answer to another (the Wave-A trap, now multiplied across tenants).

## Multi-tenancy & auth

**Firebase auth is the hard precondition for the per-user overlay** (the global graph can ship without
it). Minimal landing: Firebase ID token → `get_current_user` verifies via Admin SDK → `User.firebase_uid`
maps to a row → **`SET LOCAL app.user_id` inside each request transaction**. Isolation via **Postgres
Row-Level Security** on every overlay table keyed on `current_setting('app.user_id')`.

> **⚠️ asyncpg caveat (cross-tenant leak vector):** connections are pooled and reused across users, so the
> RLS var **must** be `SET LOCAL` inside the request transaction. A session var leaked across a reused
> pooled connection serves one user another user's scope. Prove isolation cheaply first: enable RLS on the
> *existing* overlay tables (feedback/preferences/follows/settings) when auth lands, before any graph.

## Engine — Postgres stays; user count is not the trigger

Plain **Postgres FK + recursive CTEs (depth 1–2) + pgvector rerank, one instance.** Multi-user moves
*economics*, not the *engine* — the technical crossover is **query depth / shortest-path**, a workload
NewsLens doesn't have. Benchmarks: at 43k entities (years away), 1-hop 0.4ms, 2-hop 0.5ms, 3-hop 43ms;
CTEs only collapse on shortest-path (where Neo4j wins 81–135×). **Apache AGE is ~40× slower** on shallow
traversals (its variable-length wildcard bypasses indexes). **Triggered upgrades only:** CTE→AGE if
production depth genuinely >2 hops *and* p95 >~50ms (in-place, same Postgres); Neo4j only on a real
shortest-path/centrality workload *and* ~100k+ nodes.

## Cost model

Two asymmetric streams: **(A) global extraction** — fixed daily spend, **cost/user = A/N falls** as users
grow (the whole case); **(B) per-user retrieval** — scales with N × queries × (~100 graph tokens + budgeted
bodies). The scale signal to watch is the **crossover where B overtakes A**. **Pre-commit deliverable:**
compute **N\*** = `extraction_cost_per_day / vector_baseline_cost_per_user_per_day` with real ingest/token
numbers *before* writing graph code — if you can't produce N\*, you're guessing at amortization. Never:
per-user graphs (re-couples A to N), batch rebuilds (turns A into per-cycle full-corpus), uncapped hops.

## Build trigger — all four must hold (none do today)

1. **Auth landed** — Firebase un-parked, real `user_id`s, RLS live on existing overlay tables.
2. **Real user base** — ~**50–100+ WAU**, i.e. enough that modeled amortized extraction/user < the vector-only baseline (use **N\***, don't guess).
3. **Surviving multi-hop need** — Wave D Phases 1–2 shipped *and* the intent router logs show relational/cross-cutting questions are **≥ ~15–20%** of real queries that focal+vector recall demonstrably fails. (Attach the number, or "multi-hop need" is a vibe.)
4. **Resolution gate** — >85% (target 0.90–0.95) on a labeled sample, as a **continuous monitored SLO**, before the graph feeds any lens.

The **per-user overlay** additionally **hard-blocks on (1)**. Until all four hold, the correct answer is
Wave D Phases 1–2 with **no graph**.

## Phasing (continues from Wave D)

| Phase | Scope | Gate |
|---|---|---|
| **D1** | Wave D Phase 1 — `extracted_text` + `build_context()` seam + neighbour recall (frameworks-first) | none (ship now) |
| **D2** | Wave D Phase 2 — `cluster_edges` + "how we got here" | none |
| **A** | Auth: Firebase + `firebase_uid` + `SET LOCAL` + RLS on existing overlay tables | gates the overlay only |
| **G1** | GLOBAL graph (entities/events/edges + incremental extractor + resolution SLO + reversible merges) — helps even `user_id=1` | build-trigger (1–4) |
| **G2** | PER-USER overlay (relevance, `Follow→entity_id`, RLS ask history) | **hard-blocked on A** |
| **G3** | Hybrid retrieval (intent-routed CTE recall → overlay filter → pgvector rerank) = the KNOWLEDGE_DEPTH_ENGINE | after G1 |

## Migration path (clean — two seams to respect)

The graph rides **on top of** D1's `extracted_text` + `build_context()` (extraction reads the body the seam
already retrieves) and reuses D2's `cluster_edges` (events derive from clusters). All global tables are
purely **additive** (no `user_id` → never re-tenants content). **The one hazard:** migrate `Follow.value`
(free-text) → `entity_id` FK, and the **re-pointing step must ship in the merge job BEFORE the first
production auto-merge**, or the first merge silently orphans follows. Keep `uq_follow(user_id,kind,value)`
through the nullable-backfill window.

## Decisions (resolved)

| # | Question | Decision |
|---|---|---|
| 1 | Shared global graph vs graph-per-user? | **Shared global + thin per-user overlay** (overlay = JOIN/filter). Per-user graphs destroy amortization. |
| 2 | Does multi-user change the engine? | **No** — Postgres FK + CTEs + pgvector. User count = economics; crossover = query depth. |
| 3 | Build the graph now? | **No — gate** on auth + ~50–100 WAU (N\*) + ≥15–20% multi-hop + >85% resolution. |
| 4 | Is auth required first? | **For the overlay, yes** (hard block). The global graph can ship under `user_id=1`. |
| 5 | Tenant isolation? | **Postgres RLS + `SET LOCAL` per request txn** (asyncpg pooling → cross-tenant leak otherwise). |
| 6 | Resolution gate enough at 85% one-time? | **No — raise to 0.90–0.95 auto-merge + continuous SLO + reversible merges + human-in-loop**; shared-graph blast radius. |
| 7 | Batch GraphRAG or incremental? | **LightRAG-style incremental merge-on-ingest.** Batch is fatal for a 10-min feed. |
| 8 | Follows surviving merges? | **Stable `entity_id` FK + re-pointing step (provenance-logged), shipped before first auto-merge.** |

## Risks

- Building the graph before D1–D2 → reasons over truncated headlines (the exact single-user trap, now with multi-tenant blast radius).
- Shared bad-merge blast radius treated as a launch checkbox → silent degradation on feed drift (15–20%/quarter). Continuous SLO + reversible merges.
- RLS var leaking across pooled asyncpg connections → cross-tenant data leak. `SET LOCAL` inside the txn, always.
- Treating user growth as a Neo4j/AGE trigger → premature; AGE is ~40× slower on shallow traversals here.
- Per-user graphs / per-user materialized subgraphs → destroys amortization.
- Overlay relevance leaking into the global graph (or vice-versa) → collapses isolation + un-shares the cache.
- Cache staleness multiplied across tenants → widen the hash to include user scope.
- Carrying the debunked "free GDELT entities / reused centroids" claims → they're real new cost; price them.

## Bottom line + three hardening demands (for when the gates pass)

The architecture is the boring, reversible, stack-fitting choice and honors people→products→profits (auth
gates the overlay; D1 ships value to today's single user and is rework-free; the graph is the at-scale
moat, last). Before it's build-ready: **(1)** produce **N\*** as a hard pre-commit number, not a footnote;
**(2)** attach a **logged percentage** to "surviving multi-hop need" via the intent router; **(3)** order
the **Follow re-pointing** step before the first production auto-merge. Until all four gates hold — and
none do on 2026-06-24 — keep shipping **Wave D Phase 1, frameworks-first, no graph.**

## Sources
[GraphRAG amortization](https://medium.com/graph-praxis/the-graphrag-cost-cliff-how-33-000-became-33-in-eighteen-months-be1b0fbe37e4) · [LightRAG incremental](https://www.ragdollai.io/blog/lightrag-vector-rags-speed-meets-graph-reasoning-at-1-100th-the-cost) · [entity-resolution blast radius](https://www.sowmith.dev/blog/graphrag-entity-disambiguation) · [pgvector + CTEs vs Neo4j/AGE](https://www.pedroalonso.net/blog/graphrag-vs-vector-postgres/) · [Postgres RLS multi-tenancy](https://www.crunchydata.com/blog/row-level-security-for-tenants-in-postgres)
