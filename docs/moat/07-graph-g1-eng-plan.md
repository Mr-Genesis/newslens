# Wave D Phase 3 — G1: Global Entity Backbone (engineering plan)

## NewsLens G1 â€” The Entity Backbone (final engineering plan)

### Positioning: what G1 is, and what it is NOT

G1 is **an entity backbone over the clusters that already exist** â€” *"who/what is in this story, and what other recent stories touch the same people/orgs/places."* It ships the leanest cut that delivers real single-user value: **co-occurrence over exact+alias resolution**, no embedding NN, no auto-merge, no typed-edge graph.

After the engineering and product reviews, the build is deliberately leaner than the draft:

- **DEFERRED to G2/G1.5** (defending scale/sharing that does not exist yet): reversible auto-merge + `entity_merge_log` + tested unmerge (draft S5/S6), the `entities.embedding` column **and its HNSW index**, the embedding-NN tie-breaker, and the followâ†’entity re-point/orphan-guard.
- **DEFERRED to G3** (gated engine): `entity_edges`, `events`, `user_entity_relevance` + RLS on entity tables, recursive-CTE traversal, intent router, SLO dashboard, the `N*` amortization deliverable.

Final G1 = **3 global content tables** (`entities`, `entity_aliases`, `article_entities`) + **one new service** (`entities.py`) + **one decoupled scheduler job** + **two pure-SQL read endpoints** + **a frontend chip row**. Extraction is a single JSON-mode LLM pass per *settled, changed* cluster, run as its own APScheduler interval job â€” **not** inside the clustering hot loop.

### Gate note (kept visible, honest)

The full graph (G3 multi-hop engine + G2 per-user overlay) is gated on: **auth landed** (done â€” Firebase + `app.user_id` GUC + RLS on the four overlay tables are live), **~50â€“100 WAU**, **>=15â€“20% logged multi-hop demand**, and a **>85% resolution SLO**. G1 ships under the owner's directive as the cheap, single-user-valuable substrate. The `N* = extraction_cost_per_day / vector_baseline_per_user_per_day` amortization number is a **pre-commit deliverable for G3, not for G1** â€” G1 just keeps the numerator low (extract once per settled cluster, on-change only, salient-only, platform key, gpt-4o-mini).

A one-line code-comment breadcrumb goes on `entities.py`: *any future lens that reads graph output must widen its `_source_hash` to include entity ids + content version + persona/depth + (at G2) user scope.* **Zero G1 implementation** â€” both G1 endpoints are uncached pure-SQL reads.

---

### Schema (Alembic-owned in prod; `create_all` builds it in tests â€” existing parity discipline)

Three additive, **global, non-RLS** tables (shared content, exactly like `articles`/`story_clusters`/`cluster_edges`). They are NOT added to `_RLS_TABLES` (models.py:321). New ORM models in `models.py` + one Alembic migration `down_revision="c9d0e1f2a3b4"` (verified head = `wave_d_rls`) whose `upgrade()` mirrors the ORM â€” the `f6a7b8c9d0e1` cluster_edges migration is the precedent.

**PK/FK types match the existing schema:** every current model uses `Integer` PKs/FKs (Article, StoryCluster, ClusterEdge all `mapped_column(Integer, primary_key=True)`). The new tables use `Integer` too, and `article_entities.article_id` is `Integer` to match `articles.id` exactly â€” **no int4/int8 mismatch**, and the parity test (`test_alembic_baseline_matches_models`) stays green.

**`entities`** â€” `kind` is a string-by-convention column (matches `ClusterEdge.kind`/`Follow.kind`), no PG enum. **No `embedding` column in G1** (deferred with the NN tie-breaker to G2) â€” so **no HNSW index**, which means the parity test's hardcoded `_is_hnsw` allowlist (test_foundation.py:182) needs no change in G1.

**`entity_aliases`** â€” `lower(alias)` index is the zero-vector-cost resolution path.

**`article_entities`** â€” the one relation that delivers the headline value. `UniqueConstraint(article_id, entity_id)` makes re-extraction idempotent (mirrors `uq_cluster_article`). `ix_article_entities_entity` powers the reverse "appears in" lookup. `article_id` FK is `ON DELETE CASCADE` (mentions die with the article â€” the sane default for a derived table; confirm articles are not hard-pruned today, but set CASCADE for safety regardless).

`entity_merge_log` is **NOT created in G1** (it lands with auto-merge in G2).

---

### Extraction pipeline â€” decoupled backfill job (corrected seam)

**The draft's seam was wrong.** Hooking extraction into `run_clustering`'s new-cluster `else:` branch (clustering.py:64â€“81) is broken three ways: (1) the cluster is created from a **single seeding article** (`StoryCluster(title=article.title)`, clustering.py:66) and never re-extracted as corroborating sources arrive â€” so entities come from one thin article forever; (2) the surrounding session is **already committed** at clustering.py:75 and `link_cluster` commits **again** at clustering.py:129, so extraction would inherit an indeterminate transaction; (3) it injects LLM latency into the 10-min clustering loop, which on APScheduler defaults (`max_instances=1`) means a slow batch **skips the next clustering run** and silently starves clustering.

**Corrected design â€” model it on `summarizer.backfill_summaries`** (summarizer.py:152â€“188), the existing decoupled-backfill precedent:

- New `backfill_entities()` in `services/entities.py`, registered as its **own** APScheduler interval job in `start_scheduler` (main.py:131â€“195) with explicit `max_instances=1, coalesce=True, misfire_grace_time=...`, so it can never overlap itself or starve clustering.
- It selects clusters that are **settled** (`source_count >= 2` OR age > N min) **and changed** (stored graph `source_hash` != current `_source_hash(articles)`), capped per run (`graph_extract_batch_size`), exactly like `backfill_summaries` selects stale ids then processes each in its own session.
- Each cluster is processed in **its own fresh `async with async_session() as s:`** with a single explicit transaction wrapping resolve â†’ persist `article_entities` â†’ write the source-hash â€” one commit. This is independent of the (already-committed) clustering session.

**On-change skip:** reuse the lens cache discipline. Compute `source_hash = lenses._source_hash(articles)` (verified at lenses.py:62), store the last-extracted hash on the cluster in `extra_json` under subkey `graph` via the existing server-side JSONB-merge `_cache_write` (lenses.py:235), and skip when unchanged. A settled, unchanged cluster is a no-op.

**Input:** `retrieval.cluster_text(cluster, articles, depth_pref="standard")` (verified signature, keyword-only `depth_pref`, retrieval.py:36) â€” full `extracted_text` bodies (Wave D1), never headlines.

**Cost levers (priority order):** (1) once per settled cluster, on-change only; (2) salience cap 8â€“12 entities, floor 0.3 â€” salient WHO/WHAT/WHERE only, never every proper noun; (3) **platform key** (see below); (4) gpt-4o-mini + JSON mode; (5) gleaning OFF (single pass).

**LLM call shape â€” corrected framing:** `llm.generate` does **not** enforce a structured schema. The `schema` arg (llm.py:116â€“117) is used **only as a truthy flag** to set `response_format={"type":"json_object"}` (and `response_mime_type` on the Gemini path); the dict contents are ignored. So this is **"JSON-mode + Pydantic validation"**, not "schema-constrained". The prompt text must fully carry the `{entities:[{canonical_name,kind,salience,aliases}]}` shape, and `EntityExtraction.model_validate(raw)` (new in `schemas.py`, mirroring `StoryImpact`) is the **only** real shape guard. On validation failure: log + skip, never raise.

**Platform key â€” corrected (the draft's claim was factually false):** the draft asserted a background job falls back to env `OPENAI_API_KEY` because the GUC is unset. It does **not**. `embeddings._get_user_api_key()` (embeddings.py:24â€“59) queries `UserSetting WHERE user_id==1 AND verified` **unconditionally â€” no GUC check** â€” and returns user 1's per-user key if set. In this single-user app the owner very likely *has* set one, so extraction would bill the owner's personal key, breaking the amortization premise. **Fix:** add a real platform-key seam â€” a `force_platform_key: bool = False` kwarg threaded through `llm.generate` â†’ `_generate_openai`, which when true uses `settings.openai_api_key` directly (a `_get_client_platform()` helper) and **bypasses** `_get_user_api_key`. `entities.py` calls `llm.generate(..., force_platform_key=settings.graph_use_platform_key)`. A test asserts a background extraction does **not** read user 1's key.

**Config additions** (`config.py`, defaults): `graph_extraction_model="gpt-4o-mini"`, `graph_extraction_enabled=False` (ship dark), `graph_max_entities_per_cluster=12`, `graph_salience_floor=0.3`, `graph_extract_batch_size=20`, `graph_extract_min_sources=2`, `graph_use_platform_key=True`.

---

### Entity resolution (G1: exact + alias only, precision-biased)

Per-entity resolution inside the per-cluster extraction transaction:
1. **Exact canonical match** â€” `lower(canonical_name)` against `ix_entities_kind_name` (kind + name). Zero vector cost.
2. **Alias match** â€” `lower(alias)` against `ix_entity_aliases_alias`.
3. **Miss â†’ create a new entity** + insert its aliases.

**No embedding NN, no auto-merge in G1.** Per the product review (and the draft's own cost/benefit): a missed merge just leaves *two thin nodes* â€” cosmetically two chips instead of one â€” which is an acceptable single-user blemish, not a launch blocker. A *false* merge corrupts a shared read, but **there is no shared graph and no second reader yet**. So G1 simply never merges. The embedding column, HNSW index, NN tie-breaker, confidence bands, `entity_merge_log`, reversible unmerge, and the follow re-point all move to **G2**, where entity volume makes dupes visible and the overlay JOINs make precision matter. This removes ~40% of the draft's build and drags zero embedding-generation cost into G1.

---

### Retrieval / endpoint integration

Two read endpoints, mirroring the `/clusters/{cluster_id}/...` + `Depends(get_current_user)` pattern (verified routes.py:1158â€“1214). Both are **pure SQL, no LLM** â€” they read the backbone, not generate it.

1. **`GET /clusters/{cluster_id}/entities`** â€” the cast strip / earliest visible win. Joins `article_entities` â†’ `entities` for the cluster's articles, dedups by entity (max salience), orders by salience, caps at `graph_max_entities_per_cluster`. Returns `[{id, canonical_name, kind, salience}]`. Auth-gated for consistency; data is global.

2. **`GET /entities/{entity_id}/clusters`** â€” the "appears in" rail. Reverse lookup on `ix_article_entities_entity`: other recent clusters whose articles mention this entity, ordered by `story_clusters.created_at` recency, capped at 10. Co-occurrence delivers ~90% of the connecting-tissue value with **zero graph engine and zero edges table**. (The D2 `cluster_edges` timeline remains the temporal-ordering precedent; G1 reuses recency, not a new edge type.)

**Why no recursive CTE / edges:** "how entities connect" is a depth-1 co-occurrence JOIN over `article_entities` â€” that *is* the single-user win. Multi-hop optimizes a workload with zero logged demand â†’ G3, gated.

**Frontend:** add `getClusterEntities(clusterId)` + `getEntityClusters(entityId)` to `frontend/src/lib/api.ts` (mirroring `getFrameworks`); render a tappable chip row in `frontend/src/components/DeepDiveView.tsx` (alongside frameworks/impact) linking each entity to its "appears in" rail. **Slice 1 ships this visible chip row** â€” not invisible plumbing.

---

### Test-harness reality (corrected â€” these were over-claimed in the draft)

- **Endpoint slices are NOT MockSession-testable.** `MockSession.execute` (conftest.py:166â€“187) dispatches only by `column_descriptions` entity for `StoryCluster`/`Topic`/`Article`, else returns `feed_articles`. The new endpoints are column-tuple JOINs over `article_entities`â†’`entities` â€” no recognized entity match â†’ garbage/empty. **All G1 service + endpoint slices use the real async-DB integration harness** (`db_session`/`aclient` in `tests/integration/conftest.py`), like the existing foundation tests.
- **`fake_llm` needs a new branch.** Integration `fake_llm._schema_shape` (conftest.py:80â€“194) sniffs prompt cues for lens shapes and returns `{"result":"generic"}` otherwise â€” which would fail `EntityExtraction.model_validate`. Add a branch that returns a valid `{entities:[{canonical_name,kind,salience,aliases}]}` payload when it sees the extraction prompt cues.
- **`EXPECTED_TABLES`** in `tests/integration/test_foundation.py:19` gets the 3 new tables added so the upgrade test covers them.
- **No `_is_hnsw` change in G1** (the entities embedding/HNSW index is deferred to G2; the allowlist widening moves to G2 with that index).

---

### TDD slice breakdown (ordered for earliest visible win)

Slices 1â€“4 deliver the full visible win ("who/what is in this story" + "what else touches them") using only exact+alias resolution â€” before any embedding/merge/follow complexity. Each slice: a RED test first, then minimum GREEN. Details, RED tests, GREEN impls, and real file paths are in the `slices` field.

Final G1 slice set: **S0** schema + parity, **S1** cast-strip endpoint (visible win), **S2** "appears in" rail endpoint, **S3** extraction prompt + `EntityExtraction` validation + fake_llm branch, **S4** exact+alias resolution + idempotent persist, **S5** decoupled backfill job (on-change, settled-only, own session/txn) + scheduler registration, **S6** platform-key seam, **S7** followâ†’entity resolution hook (resolution only â€” no column, no re-point), **S8** frontend chip row.

---

### Risks

See the `risks` field.

---

## Schema tables

### `entities`
Global, content-scoped node: a salient person/org/place/other extracted from cluster articles. NOT RLS-scoped (shared content). No embedding column in G1 (NN tie-breaker deferred to G2).

- `id INTEGER PK`
- `canonical_name TEXT NOT NULL`
- `kind TEXT NOT NULL  -- string-by-convention {person,org,place,other}, no PG enum`
- `description TEXT NULL`
- `first_seen TIMESTAMPTZ`
- `last_seen TIMESTAMPTZ`
- `mention_count INT DEFAULT 0`
- `Index ix_entities_kind_name (kind, lower(canonical_name))  -- exact resolution pre-filter`

### `entity_aliases`
Alternate surface forms for an entity (e.g. 'RBI' -> 'Reserve Bank of India'). The zero-vector-cost second resolution lookup.

- `id INTEGER PK`
- `entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE`
- `alias TEXT NOT NULL`
- `source TEXT NULL`
- `UniqueConstraint(entity_id, alias) uq_entity_alias`
- `Index ix_entity_aliases_alias (lower(alias))`

### `article_entities`
The one relation that delivers the headline value: which entity is mentioned in which article, with salience. Powers both the cast strip and the reverse 'appears in' rail.

- `id INTEGER PK`
- `article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE  -- matches articles.id Integer type exactly`
- `entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE`
- `salience REAL DEFAULT 0`
- `confidence REAL DEFAULT 0`
- `UniqueConstraint(article_id, entity_id) uq_article_entity  -- idempotent re-extraction`
- `Index ix_article_entities_entity (entity_id)  -- reverse lookup for the appears-in rail`

## TDD slices

### S0 — Schema: entities + entity_aliases + article_entities (ORM + Alembic + parity)
- **RED:** In tests/integration/test_foundation.py add EXPECTED_TABLES |= {'entities','entity_aliases','article_entities'} and assert test_alembic_upgrade_from_empty_creates_all_tables still finds them after upgrade to head; assert test_alembic_baseline_matches_models yields zero drift (no _is_hnsw change needed â€” no embedding/HNSW index in G1). Add a direct-DB test that inserts an entity, an alias, and an article_entities row and reads them back, asserting the uq_article_entity unique constraint rejects a duplicate (article_id,entity_id).
- **GREEN:** Add three ORM models to backend/app/models.py using Integer PKs/FKs (matching Article/StoryCluster), kind as String(16) by convention (like ClusterEdge.kind), ON DELETE CASCADE on the two article_id/entity_id FKs, the named unique constraints and the two lower() indexes. Do NOT add them to _RLS_TABLES. Generate one Alembic migration with down_revision='c9d0e1f2a3b4' (verified head wave_d_rls) whose upgrade() mirrors the ORM exactly.
- **Files:** backend/app/models.py, backend/migrations/versions/<new>_g1_entity_backbone.py, backend/tests/integration/test_foundation.py

### S1 — GET /clusters/{id}/entities â€” the cast strip (earliest visible win)
- **RED:** Integration test (db_session/aclient + fake_llm): seed a cluster with 2 articles and article_entities rows for 3 entities at varying salience; GET /clusters/{id}/entities; assert 200, entities deduped by entity, ordered by salience desc, capped at graph_max_entities_per_cluster, shape [{id,canonical_name,kind,salience}]. (NOT MockSession â€” column-tuple join is unsupported there.)
- **GREEN:** Add a pure-SQL reader in entities.py (cluster_entities(db, cluster_id)) joining article_entities->entities for the cluster's articles, GROUP BY entity taking max(salience), ORDER BY salience DESC, LIMIT cap. Add @router.get('/clusters/{cluster_id}/entities', dependencies=[Depends(get_current_user)]) in routes.py mirroring cluster_frameworks.
- **Files:** backend/app/services/entities.py, backend/app/api/routes.py, backend/tests/integration/test_entities_api.py

### S2 — GET /entities/{id}/clusters â€” the 'appears in' rail
- **RED:** Integration test: seed entity E mentioned in articles across clusters C1 (older) and C2 (newer); GET /entities/{E}/clusters; assert clusters returned newest-first by story_clusters.created_at, capped at 10, shape [{cluster_id,title,created_at}], and that a cluster where E is NOT mentioned is absent.
- **GREEN:** Add entity_clusters(db, entity_id) in entities.py: reverse lookup on ix_article_entities_entity joining article_entities->cluster_articles->story_clusters, DISTINCT cluster, ORDER BY created_at DESC LIMIT 10. Add @router.get('/entities/{entity_id}/clusters', dependencies=[Depends(get_current_user)]).
- **Files:** backend/app/services/entities.py, backend/app/api/routes.py, backend/tests/integration/test_entities_api.py

### S3 — Extraction prompt + EntityExtraction validation + fake_llm branch
- **RED:** Unit test: EntityExtraction.model_validate on a well-formed {entities:[{canonical_name,kind,salience,aliases}]} payload succeeds and clamps kind to {person,org,place,other}; a malformed payload raises (caller will skip). Integration test: fake_llm._schema_shape returns a valid entities payload when fed the extraction prompt cues (today it returns {'result':'generic'} which would fail validation).
- **GREEN:** Add EntityExtraction Pydantic model to schemas.py (mirrors StoryImpact). Add build_extraction_prompt(cluster_text) in entities.py that fully specifies the JSON shape in prose (since llm.generate's schema arg is only a json_object truthy flag, not enforcement). Add an entities branch to fake_llm._schema_shape in tests/integration/conftest.py returning a deterministic valid payload.
- **Files:** backend/app/schemas.py, backend/app/services/entities.py, backend/tests/integration/conftest.py, backend/tests/test_entities.py

### S4 — Exact + alias resolution + idempotent persist (one transaction)
- **RED:** Integration test: extract entities for a cluster twice over the same article set; assert (a) exact-name + alias resolution reuses the existing entity (no duplicate row), (b) re-running is idempotent (uq_article_entity prevents dup mentions), (c) a new salient entity creates a new row + its aliases. All within one committed transaction per cluster.
- **GREEN:** resolve_and_persist(s, cluster_id, articles, extraction) in entities.py: per entity, try lower(canonical_name) on ix_entities_kind_name, then lower(alias) on ix_entity_aliases_alias, else INSERT entity + aliases; upsert article_entities (ON CONFLICT DO NOTHING on uq_article_entity). No embedding NN, no merge in G1. One async_session() + one commit.
- **Files:** backend/app/services/entities.py, backend/tests/integration/test_entities.py

### S5 — Decoupled backfill job: on-change, settled-only, own session/txn + scheduler
- **RED:** Integration test (model on backfill_summaries): seed one settled cluster (>=2 sources) with no graph source_hash and one whose stored graph hash == current _source_hash(articles); run backfill_entities(); assert only the changed/settled cluster was extracted (fake_llm generate count == 1) and the unchanged one was skipped; assert a single-article (unsettled) cluster is skipped. Assert each cluster runs in its own session and the stored source_hash is written via the JSONB merge.
- **GREEN:** Add backfill_entities() in entities.py mirroring summarizer.backfill_summaries: select settled (source_count>=graph_extract_min_sources OR age>N) clusters whose stored extra_json.graph.source_hash != lenses._source_hash(articles), capped at graph_extract_batch_size; process each in its OWN async_session() with one transaction (resolve_and_persist + write source_hash via lenses._cache_write into extra_json subkey 'graph'); never touch run_clustering's session. Register in start_scheduler (main.py) as its own interval job id='entity_backfill' with max_instances=1, coalesce=True, misfire_grace_time set. Guard the whole job behind settings.graph_extraction_enabled.
- **Files:** backend/app/services/entities.py, backend/app/main.py, backend/tests/integration/test_entities.py

### S6 — Real platform-key seam (force_platform_key) â€” fixes the amortization bug
- **RED:** Integration test: seed UserSetting(user_id=1) with a verified per-user OpenAI key; call the extraction path with a spy on embeddings._get_user_api_key; assert it is NOT invoked and settings.openai_api_key is used (the platform key), proving extraction does not bill the owner. Assert llm.generate(force_platform_key=True) bypasses the per-user resolver.
- **GREEN:** Add force_platform_key: bool=False kwarg to llm.generate -> _generate_openai; when true, build the client from settings.openai_api_key directly (new _get_client_platform() in embeddings.py) bypassing _get_user_api_key. entities.py calls llm.generate(..., force_platform_key=settings.graph_use_platform_key). (Gemini path: same flag bypasses _resolve_gemini_key, using settings.gemini_api_key.)
- **Files:** backend/app/services/llm.py, backend/app/services/embeddings.py, backend/app/services/entities.py, backend/tests/integration/test_entities.py

### S7 — Follow -> entity resolution hook (resolution only; no column, no re-point)
- **RED:** Integration test: create an entity-kind Follow whose value matches an existing entity's canonical_name; assert the follow-creation path resolves it to that entity_id and records the resolution opportunistically WITHOUT requiring a follows.entity_id column and WITHOUT mutating follows in any merge path (no merge exists in G1). Assert no follows schema change is emitted by autogenerate.
- **GREEN:** On entity-kind follow creation in routes.py, call entities.resolve_existing(value) (exact+alias lookup, returns entity_id or None) and log/return it for the rail; do NOT add a follows.entity_id column and do NOT include follows in any FK re-point (auto-merge is deferred to G2, so there is nothing to re-point). This keeps the cheap forward-compat hook and resolves the draft's S7 contradiction by cutting the merge half.
- **Files:** backend/app/api/routes.py, backend/app/services/entities.py, backend/tests/integration/test_entities_api.py

### S8 — Frontend: entity chip row in DeepDiveView + api client
- **RED:** Vitest: getClusterEntities(clusterId) and getEntityClusters(entityId) call the correct paths with the env-aware base URL (mirror the getFrameworks test). Component test: DeepDiveView renders a chip per entity (ordered by salience) and each chip links to the entity's appears-in view; empty/unavailable entity list renders nothing (graceful).
- **GREEN:** Add getClusterEntities + getEntityClusters to frontend/src/lib/api.ts mirroring getFrameworks. Render a tappable chip row in frontend/src/components/DeepDiveView.tsx alongside the frameworks/impact sections; each chip routes to the entity's appears-in rail. Hide the section when the list is empty.
- **Files:** frontend/src/lib/api.ts, frontend/src/components/DeepDiveView.tsx, frontend/src/components/DeepDiveView.test.tsx

## Risks
- Extraction recall is exact+alias-only in G1 (embedding NN deferred). Distinct surface forms the model does not emit as aliases (e.g. 'RBI' vs 'Reserve Bank of India' when only one is produced) create two thin nodes. Accepted, single-user blemish â€” not a launch blocker; the merge/NN machinery earns its place in G2 when entity volume makes dupes visible AND the overlay JOINs make precision matter.
- Platform-key seam is load-bearing for the cost story and must be a REAL code path. The current llm.generate -> embeddings._get_user_api_key() unconditionally reads user 1's verified key (no GUC check). If S6 is skipped or the force_platform_key flag is not threaded all the way through, every background extraction silently bills the owner's personal key and the amortization framing is false. S6's spy test is the guard.
- Decoupled backfill job shares the same async_session factory as five other jobs; if graph_extract_batch_size or the LLM latency is large, the entity job's own runs could pile up. Mitigated by max_instances=1 + coalesce=True + a hard per-run cap, and by running on its own interval so it can never starve clustering (the failure mode the draft's coupled seam would have caused).
- llm.generate offers JSON-mode only, not schema enforcement (the schema arg is a truthy json_object flag). EntityExtraction.model_validate is the sole shape guard, so a model that returns valid JSON of the wrong shape is silently skipped (logged). Acceptable for a dark-shipped backbone; monitor skip rate before flipping graph_extraction_enabled on.
- ON DELETE CASCADE on article_entities.article_id assumes mentions should die with the article. If the ingestion pipeline ever hard-deletes articles that are still referenced elsewhere, mention counts shift silently. Confirm whether articles are hard-pruned; CASCADE is the safe default either way.
- The on-change source_hash is stored in extra_json under subkey 'graph' via the same JSONB-merge path the lenses use. A future lens that reads graph output MUST widen its own _source_hash to include entity ids + content version (+ user scope at G2) or it will serve stale/cross-tenant answers. G1's two endpoints are uncached pure-SQL reads so the trap does not bite yet â€” captured as a code-comment breadcrumb only.
- Deferring the embedding column to G2 means adding it later is a non-trivial migration + backfill (populate embeddings for the existing entity corpus before NN resolution is meaningful). This is the deliberate trade for not dragging embedding-generation cost into G1; flag it in the G2 plan as a backfill prerequisite.

## Cost
G1 LLM cost is bounded by one gpt-4o-mini JSON-mode pass per SETTLED, CHANGED cluster (not per article, not per clustering tick) â€” collapsing the firehose to ~hundreds of clusters/day at most, each capped at 8-12 salient entities, single pass (gleaning off), on the platform key (env OPENAI_API_KEY via the new force_platform_key seam), never the owner's per-user key. No embedding generation cost in G1 (the entities.embedding column and HNSW index are deferred to G2 with the NN tie-breaker), so G1 adds zero new vector spend. The two read endpoints are pure SQL (no LLM, uncached). The N* amortization number is a G3 pre-commit deliverable, not a G1 artifact; G1's job is to keep the numerator low so that number looks good when G3's gate is evaluated.

---
_Generated by the graph-g1-eng-plan workflow (8 agents: codebase + scope + research + first-principles → design → eng/product review → finalize). 26 corrections applied._

