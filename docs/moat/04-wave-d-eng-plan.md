# Wave D — Engineering Plan: Knowledge Depth (make the deep dive stop being thin)

> Parent: [`00-PLAN.md`](00-PLAN.md). The deferred "depth engine". Researched + designed +
> adversarially stress-tested (GraphRAG landscape · foundation audit · first-principles feasibility
> · boring-by-default review). **Headline: the handover's framing was wrong, and the real fix is
> small.** Full GraphRAG is rejected for this app.

## The diagnosis (verified against the code)

The handover said the deep dive is thin because retrieval is shallow, and implied a knowledge
graph + GraphRAG would fix it. **The actual root cause is upstream and much cheaper to fix:**

- **The article body is destroyed at ingestion.** `gdelt.py:122` keeps `extracted[:300]`; `fetcher.py:254` keeps `summary[:300]`. `Article` has only a `snippet` column (≤300 chars) — **no body column at all**.
- So the lens `snippet[:400]` slice (`_cluster_text`) is **a provable no-op** — it's slicing a column that's already ≤300 chars. Widening it does nothing.
- **`frameworks()` reads ZERO article text** — only `cluster.title` + `cluster.summary`. (Smoking gun: that's why framework lines feel like headline restatements.)
- A graph can only reason over what retrieval surfaces. **Fixing the graph while bodies are still truncated would deepen nothing.**

**Therefore Wave D ≠ "build a knowledge graph." Wave D = stop throwing away the body + retrieve across sources.** A graph is an opt-in, gated *last* phase, only if a real multi-hop need survives.

## Capability atoms (what depth actually requires)

1. Store the full extracted body at ingest (`Article.extracted_text`) instead of discarding trafilatura's output.
2. A **single retrieval seam** (`services/retrieval.py::build_context`) that all five lenses route through — replacing the per-snippet concatenation with budgeted full bodies + vector-recalled neighbour clusters.
3. Per-source + total **token budget** so full bodies fit one LLM call without cost blow-up.
4. **Depth ladder = a retrieval budget** keyed on the *existing* `persona.depth_pref` (brief/standard/expert), not a new engine.
5. **Widen the cache hash** to cover the full retrieved id set (+ a content version) and key cache subkeys by `depth_pref` — or multi-cluster retrieval silently serves stale answers.
6. (Phase 2) Temporal `cluster_edges` over the clusters that already exist → a "how we got here" timeline.
7. (Phase 3, opt-in) A lightweight entity/event layer + hybrid recursive-CTE recall — *only if justified*.

## Phasing — cheapest-first (the 80/20 is Phase 1)

| Phase | Scope | Cheap-first |
|---|---|---|
| **0 — Measure** | Log the length distribution of stored `snippet` vs un-truncated `trafilatura.extract` on 20–30 live articles; count how many RSS items lack a fetchable body. Confirms the missing-body hypothesis before any migration. | ✅ |
| **1 — Full-body capture + retrieval seam** (the depth win) | `Article.extracted_text` (1 additive nullable column); stop truncating at ingest; `services/retrieval.py build_context()` with per-source budgeting + vector neighbour recall + depth ladder; route all 5 consumers through it (**frameworks first**); widen cache hash + `depth_pref` subkeys. **No graph.** | ✅ |
| **2 — "How we got here" over the existing cluster graph** | `cluster_edges` (successor/background/duplicate) populated by the existing clustering job; a timeline lens written to `extra_json` (no migration for the lens). | ✅ |
| **3 — Opt-in entity/event graph + hybrid retrieval** (gated) | Entity/Event/ArticleEntity/EntityEdge tables; LLM extraction + alias resolution; recursive-CTE graph recall → pgvector rerank for multi-hop questions; intent routing; wire entity follows/watchlist. **Ship only if a multi-hop need survives Phases 1–2 AND entity-resolution accuracy gates >85%.** | ❌ |

## Schema (additive, per phase)

- **Phase 1:** `Article.extracted_text TEXT NULL` (full body, cap ~16k chars; `snippet` stays ≤300 for cards). Optional `Article.content_version SMALLINT DEFAULT 1` (deferred — only needed at scale-out, to fold into the cache hash after a backfill).
- **Phase 2:** `cluster_edges(id, src_cluster_id FK, dst_cluster_id FK, kind ENUM('successor','background','duplicate'), score FLOAT, created_at; UNIQUE(src,dst,kind))` — directed edges between *existing* clusters.
- **Phase 3 (opt-in):** `entities`, `entity_aliases` (name normalization), `article_entities` (salience/confidence), `events` (derive from cluster — a cluster ≈ an event), `entity_edges` (time-stamped). pgvector `ivfflat`/`hnsw` on entity/event embeddings (reuse the existing Article config). **Entity-light** — only salient entities, never every noun.

## Retrieval seam + depth ladder

`services/retrieval.py::build_context(db, cluster_id, depth_pref, intent) -> ContextPack` **replaces** the `_cluster_text` / `_impact_source_lines` snippet concatenation. Assembly:
1. **Focal cluster** — full `extracted_text` per source, **budgeted per-source**, free-first ordered.
2. **Neighbour recall** — pgvector NN over `Article.embedding` for related clusters (the cross-story depth win, **no graph needed**).
3. **Historical recall** — temporal-prior clusters via `cluster_edges` (Phase 2).

Depth ladder is a **budget**: `brief` = focal only, trimmed; `standard` = focal full + 2–3 neighbours; `expert` = + historical chain + (Phase 3) one graph hop. `ContextPack` returns the exact `article_ids`/`cluster_ids` it used → that becomes the cache-invalidation input.

**Hybrid (Phase 3 only):** for explicit multi-hop questions, a depth-2/3 recursive CTE over edges returns the candidate neighbourhood (microseconds at <10k nodes), then **pgvector reranks** (graph for recall, vector for ranking — the documented 2-hop hit-rate 0.28→0.83 unlock). Simple single-story questions **skip the graph** (intent routing) to avoid noise on the common case.

## Integration (per consumer)

| Consumer | How Wave D feeds it |
|---|---|
| **`frameworks()`** | **First target, highest ROI** — reads zero article text today; feed `build_context` bodies so lines cite real claims, not the headline. No regression surface. |
| `impact()` | Swap `_impact_source_lines` → `build_context(depth_pref=persona.depth_pref)`; `persona_hash` subkey extends naturally; 2-gen guardrail loop unchanged. |
| `ask()` | Route through `build_context(intent='qa')`; intent routing sends "how did X develop/connect" to historical/graph hops, simple Qs stay focal+vector. |
| `consensus()` | Full per-source bodies so agree/dissent is judged on real claims, not 240-char blurbs. |
| `analysis/strategic/trivia` | Swap `_cluster_text` → `build_context(...).as_prompt_text()` at the same call site. |
| **"How we got here" timeline** (NEW, Phase 2) | New lens → `extra_json` subkey `timeline`: within-cluster chronology + 2–4 `cluster_edges` neighbours, one LLM call, cached. |
| Cache layer (`get_lens`/`_source_hash`) | **Widen `_source_hash`** to the full retrieved id set (+ content version) and add `depth_pref` to subkeys. |

## ⚠️ The one correctness trap (load-bearing)

`_source_hash` today hashes only the **focal cluster's** article ids. The moment retrieval pulls in neighbour/historical clusters, the JSONB-merge cache will **silently serve stale depth answers** when neighbours change. **Widen the hash before shipping multi-cluster retrieval** — the merge makes the bug invisible.

## Migration / performance

- Phase 1 = 1 additive nullable column (instant); cost is a one-time, throttled, best-effort re-fetch **backfill** (network-bound, snippet fallback, never blocks ingestion). RSS often ships no body → graceful degradation.
- Token cost is the dominant new cost once bodies enter prompts → bound by the per-source + total budget tied to `depth_pref`/`impact_max_tokens`. A deep dive ≈ 3–7 sources ≈ 5–20k tokens, one call per lens (no extra calls in Phase 1–2).
- Engine (if Phase 3): **plain Postgres FK + recursive CTEs** — at <10k nodes a depth-2/3 CTE is microseconds and ~4× faster than Neo4j on neighbourhood fan-out. **No Neo4j, no Apache AGE.**
- All migrations/retrieval validated in **Docker** (greenlet breaks native Windows-ARM); autogenerate against an empty DB.

## Decisions (resolved by the review)

1. **Root cause** — ingestion truncation, *not* the lens slice. Fix ingestion first (`snippet` is a verified no-op to widen).
2. **Graph now or defer?** — **Defer to opt-in Phase 3**, gated on a surviving multi-hop need + >85% resolution. The unwritten `INTEREST_GRAPH_SPEC`/`KNOWLEDGE_DEPTH_ENGINE` are **not committed scope**.
3. **Depth ladder** — a single retrieval budget on the existing `persona.depth_pref`, cached per depth. No separate engines.
4. **Graph engine (if ever)** — plain Postgres FK + recursive CTEs. Not Neo4j/AGE.
5. **Full Microsoft GraphRAG** — **rejected** (batch corpus-summarization + full rebuilds; ~600k tokens/query, ~2.3× latency — wrong for a single-user feed ingesting every 10–15 min).
6. **Cache** — widen `_source_hash` to the full retrieved id set + content version before multi-cluster retrieval ships.

## Risks

- **Entity resolution <85% makes a Phase 3 graph toxic** — errors compound by hop (85%→61% at 3 hops). Hard-gate on a labeled sample before the graph feeds any lens.
- **Cache staleness** (the trap above) — widen the hash.
- Re-fetch backfill hits paywalls/403s → best-effort + throttled + snippet fallback.
- Token/latency blow-up if bodies are unbounded → enforce the budget.
- Over-modeling the graph (every noun a node) → entity-light + salience filter.
- Graph staleness on a live feed (15–20%/quarter drift) → incremental merge-on-insert + temporal stamping, never full rebuilds.

## Adversarial verdict — keep / cut / defer

**Verdict: the diagnosis is right and Phase 1 is genuinely small (boring, additive, reversible); the plan is over-engineered *only* in committing the Phase 3 graph.** Two cheapness claims behind the graph were **factually wrong** and are cut:
- ❌ "Harvest GDELT entity/theme metadata at zero LLM cost" — **false**: `gdelt.py` uses `mode=artlist`, which returns URLs/titles only, **not** GKG persons/orgs/themes. The "free first pass" does not exist.
- ❌ "Phase 2 reuses the NN it already runs over cluster centroids" — **overstated**: no centroids are stored; clustering is article-to-article. Centroids are **new work**.

**Simplest first slice (do this before any retrieval module):** Phase 0 measurement, then a **frameworks-only** vertical of Phase 1 — add `Article.extracted_text`, stop truncating in `gdelt.py:122`, wire **only `frameworks()`** to read the body (it reads zero text today → pure upside, no regression), add `depth_pref` + extracted-id to its cache key. Compare framework output before/after on 5–10 clusters with full bodies. If the lines stop being headline restatements, the depth hypothesis is proven for one consumer at the cost of **one column + one prompt + one cache-key tweak**. Only then generalize `retrieval.py` to the other four and add neighbour recall.

**Keep:** Phase 0; `extracted_text` + stop truncating; the single `retrieval.py` seam; frameworks-first; depth-ladder-as-budget; cache-hash widening; vector neighbour recall; per-source budget; reject full GraphRAG; Postgres CTEs if a graph is ever built.
**Cut/defer:** all of Phase 3 (don't pre-build the tables); the false "free GDELT entities" pass; embedding `title+extracted_text` (measure-first); `content_version` + backfill (until scale-out); on-ingest RSS re-fetch (gate on Phase 0); reframe Phase 2's centroid claim as new work.

## Sources (research)
[Microsoft GraphRAG](https://github.com/microsoft/graphrag) · [LazyGraphRAG](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/) · [LightRAG cost](https://www.ragdollai.io/blog/lightrag-vector-rags-speed-meets-graph-reasoning-at-1-100th-the-cost) · [pgvector + CTEs vs Neo4j](https://www.pedroalonso.net/blog/graphrag-vs-vector-postgres/) · [GraphRAG entity disambiguation](https://www.sowmith.dev/blog/graphrag-entity-disambiguation)
