# Under-clustering & weak follow-rails share one root cause: the article vector never sees the body

**Status:** Phases 1, 3, 4 implemented (this branch); Phase 2 (threshold retune) deliberately gated on the calibration data Phase 1 now produces. Phase 3 ships **dark** (`CLUSTER_MERGE_ENABLED=false`).
**Surfaces affected:** story clustering · "News You Follow" saved-search rails · hybrid search
**Owner:** backend
**One-line:** `articles.embedding` is built from `title + snippet[:300]` only. The full body
(`extracted_text`, ≤16k chars) is captured on every row but **never embedded**, so every feature
that matches on that vector is starved of the shared signal.

---

## 1. Symptoms (two reports, one cause)

1. **"News with different title/source but almost identical content isn't clubbed together."**
   Same-event coverage from different outlets seeds separate singleton clusters instead of merging.
2. **Follow rails (saved searches) miss obviously-relevant stories.** A saved search like
   "US Iran war" fails to surface articles that are about exactly that, because the matching text the
   rail sees (title + 300-char snippet) doesn't contain the query terms even when the body does.

These look like two different bugs. They are the **same** bug seen through two different distance
regimes (doc↔doc for clustering, query↔doc for rails/search).

## 2. Root cause

The article embedding — the vector all three features compare against — is computed from
**title + card snippet only**, and the snippet is a hard 300-char slice that is nulled entirely when
it is short or tag-bearing.

| Fact | Location |
|---|---|
| Embed text = `title (+ " " + snippet)`; `extracted_text` is never read here | [`_article_embed_text`](../../backend/app/services/embeddings.py) `embeddings.py:318-322`; duplicate inline recipe in `embed_article` `embeddings.py:293-297`; prod batch path builds texts via `_article_embed_text` at `embeddings.py:368` |
| `snippet = raw[:300]` | [`fetcher.py:587`](../../backend/app/services/fetcher.py); GDELT `full[:300]` at `gdelt.py:133` |
| Snippet nulled when `< 50` chars (RSS) or short/tag-bearing (GDELT nulls snippet **and** body) | `fetcher.py:606`; `gdelt.py:80-82` |
| Full body **is** stored (`extracted_text`, Text, ≤16k) — "Wave D1: for deep retrieval" | [`models.py:140`](../../backend/app/models.py) |
| …but the body is read **only** by the deep-dive lenses, never on the embedding path | `retrieval.py:20` |

Two independent outlets writing about the same event share the event's **body** facts (names,
numbers, quotes, place) but almost always differ in **headline** and in the **first 300 chars** of
their lede. The embedding sees only the part that differs and discards the part that agrees.

### Why the same vector degrades all three surfaces

```
                      articles.embedding  =  vec( title + snippet[:300] )      ← body dropped here
                               │
        ┌──────────────────────┼───────────────────────────┐
        ▼                      ▼                           ▼
  CLUSTERING (doc↔doc)   SAVED-SEARCH RAILS (query↔doc)   SEARCH (query↔doc)
  NN < 0.15              ANN + guard 0.22 / 0.35          hybrid semantic leg
  clustering.py:151      rails.py:119-129                 routes.py /search
```

- **Clustering** — [`_find_nearest_cluster`](../../backend/app/services/clustering.py) `clustering.py:151-161`
  joins only if cosine **distance < 0.15** (similarity > 0.85). That bar is calibrated for
  near-duplicate paraphrase, not independent same-event coverage. The code itself flags that 0.15 is
  a doc↔doc number that "does NOT transfer" (`config.py:180`), and the rails feature needed far looser
  bands (0.22 / 0.35) for "semantically near."
- **Saved-search rails** — [`evaluate_saved_search`](../../backend/app/services/rails.py) `rails.py:119-129`
  runs `embedding <=> :v` ANN over the **same** starved `articles.embedding`. A body-rich article
  whose title/snippet omit the query terms sits outside the top-k, so the rail never sees it.
- **Search** — the hybrid semantic leg has the identical dependency.

Fixing the embedding input lifts **all three** at once. This is why the two reports are one fix.

## 3. Contributing / amplifying factors (verified)

Ranked, all confirmed against source by a multi-agent adversarial pass:

| # | Factor | Effect | Where |
|---|---|---|---|
| A | **Body never embedded** (root cause) | starves the vector | `embeddings.py:318` |
| B | **Snippet nulled → title-only embed** | worst case: only the headline, which every outlet writes differently | `fetcher.py:606`, `gdelt.py:80` |
| C | **0.15 clustering threshold too strict** for cross-source paraphrase | rejects genuine same-event pairs in the 0.15–0.30 band | `config.py:249` |
| D | **Single-linkage + permanent placement + no merge job** | a near-miss becomes a permanent duplicate; `link_cluster` only adds timeline edges, never merges | `clustering.py:31-40, 99-137` |
| E | **Runtime stall (operational)** | on a Gemini 429 the backfill parks 30 min; no key → hard stop. Unembedded articles are invisible to clustering — same symptom, different cause. **Check first.** | `embeddings.py:335, 371-378` |
| F | **Feed renders one row per article, not per cluster** | a correctly-clustered 3-source story shows as 3 near-identical rows → *looks* un-clustered even when it isn't. Separate UX defect. | `routes.py` `get_feed` |

**Diagnostic fork — before assuming an algorithm bug, hit `GET /pipeline`:**
- Mostly `pending`/`failed`, or `last_embedding_error` = `quota`/`no_key`/`auth` → **factor E** (runtime stall). Fix keys/quota first.
- Mostly `complete` but every cluster is a singleton → **factors A–D** (this doc's core).
- Multi-article clusters exist but the feed still shows dupes → **factor F** (presentation).

## 4. Plan (phased)

Phase 1 is the root-cause fix and the observability needed to tune the rest from real data rather
than by guessing. Phases 2–4 are gated on the calibration data Phase 1 produces.

### Phase 1 — embed the body + wire up calibration  *(this change)*
1. **Embed a bounded body window.** `_article_embed_text` folds `extracted_text[:embedding_body_chars]`
   into the vector (fallback to `snippet`, then `title`). New config `embedding_body_chars` (default
   2000; `0` restores legacy title+snippet). `embed_article` now reuses `_article_embed_text` so the
   single- and batch-paths can never drift.
2. **Log clustering near-miss distances.** `_find_nearest_cluster` now fetches the nearest clustered
   article **without** the threshold filter, logs its distance (`cluster_distance_probe`, mirroring
   rails' `rail_distance_histogram`), then applies the threshold. This exposes how many same-event
   pairs sit in the 0.15–0.30 band — the data needed to set the threshold in Phase 2.
3. **Tooling.** `scripts/reembed.py` re-embeds the existing corpus under the new recipe (quota-aware,
   batched, `--dry-run`). `scripts/measure_cluster_distances.py` histograms doc↔doc NN distances to
   calibrate the threshold.

### Phase 2 — retune thresholds from the Phase-1 data  *(config-only, reversible)*
- Raise `cluster_similarity_threshold` from 0.15 toward the knee in the observed distribution
  (expected ~0.22–0.28), optionally gated by a shared-entity/keyword confirmation for the loose band
  (mirroring the rails precision guard).
- Re-check `rails_dist_tight` / `rails_dist_loose` against `measure_follow_distances.py` — the
  richer embeddings shift the query↔doc distribution too.

### Phase 3 — cluster merge / reconcile pass  *(LANDED, dark — safety net for factor D)*
- `clustering.reconcile_clusters` (scheduled hourly, gated by `cluster_merge_enabled`): per-cluster
  **L2-normalized centroid**, pairwise cosine, **union-find** so a chain A~B~C collapses to one, with
  a **two-tier precision guard** mirroring rails — merge on a tight pure-semantic match
  (`cluster_merge_threshold_tight=0.13`) OR a looser match (`cluster_merge_threshold_loose=0.25`)
  **confirmed by a shared entity or topic**. Merge is one transaction per group: reassign
  `ClusterArticle` → survivor (most articles, tie → lowest id), drop the loser's best-effort
  `ClusterEdge` timeline links, delete the emptied `StoryCluster` (impressions CASCADE), and clear the
  survivor's stale caches (`summary`/lens JSON/`source_hash`) + `schedule_summary`. Idempotent +
  skip-tolerant; bounded to `cluster_merge_max=300` recent clusters (`cluster_merge_window_hours=72`).
  Kills the "permanent parallel singletons" trap. **Enable only after Phase 2 calibration** — it
  reassigns rows, so it's harder to reverse than a threshold bump.

### Phase 4 — collapse same-cluster siblings in the feed  *(LANDED — fixes factor F)*
- `get_feed` now collapses same-`cluster_id` articles to one representative (freshest / top-ranked, the
  first in the current sort order) **before** the page slice, so `per_page` counts **stories**, not
  articles, and `source_count` renders the "N sources" badge. Gated by `feed_collapse_clusters` (on).
  When on, the feed always paginates over the bounded pool (like the personalized path); with both
  `uer_enabled` and `feed_collapse_clusters` off, the legacy count+offset path is byte-identical.
  `get_cluster` still returns every sibling, so deep-dive is unaffected.

## 5. Rollout & validation

1. **Re-embed is mandatory after Phase 1.** Old vectors (title+snippet) and new vectors (title+body)
   live in different spaces; until the corpus is re-embedded, old↔new distances are meaningless. Run
   `python -m scripts.reembed` (needs a Gemini key + DB). On free tier this is quota-bound
   (~1,000 embeds/day) and drains over several days via the existing 5-min backfill — expected.
2. **Then calibrate before Phase 2.** Run `measure_cluster_distances.py` + read the
   `cluster_distance_probe` logs; set the threshold at the observed valley, not by guess.
3. **Existing clusters do not retro-merge** on re-embed alone (placement is permanent). Phase 3's
   merge pass — or a one-off re-cluster — is what reconciles the already-split backlog.

## 6. Risks

- **Topic dilution.** Too large a body window pulls in whole-article topic drift and can *over*-merge
  distinct events in the same domain. 2000 chars is a deliberate middle; validate with the calibration
  script before pushing it higher.
- **Batch payload size.** 50 texts × ~2k chars is larger request bodies; if batch embeds start failing
  on size, lower `embedding_batch_size` (the per-text fallback already isolates a poison text).
- **Transitional mixed space** during the re-embed window — transient, resolved once the backfill
  drains.

## 7. Provenance

Diagnosis produced by a 61-agent investigation with two-lens adversarial verification of every
hypothesis (code-mechanism + causal-impact). Every `file:line` above was checked against source.
Related note: the deep-dive "thinness" issue (body truncated for lenses) is the same family of
defect — signal discarded at/after ingestion — but a **different** consumer of the body; this doc is
specifically about the *embedding* input.
