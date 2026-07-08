# Fix Plan — "News You Follow" rails all show the same unrelated stories

| | |
|---|---|
| **Status** | Proposed — awaiting decisions in §9 before implementation |
| **Date** | 2026-07-08 |
| **Area** | `backend/app/services/rails.py` (primary), `fetcher.py`, `config.py` (secondary) |
| **Severity** | High — the entire "News You Follow" section is functionally broken (every rail identical + off-topic) |
| **Confidence** | High on *where* (over-admission in `evaluate_saved_search`); one live log check pins *which face* |
| **Verification** | 11-agent adversarial review (5 mechanisms investigated + refuted, fix synthesised) |

---

## 1. TL;DR

Every rail in the home **NEWS YOU FOLLOW** section renders the **same 5 stories in the same order**, unrelated to each rail's header, each badged "9+ NEW".

The rails are all `saved_search` (free-text) follows. Their read path — [`evaluate_saved_search`](../../backend/app/services/rails.py) — has a **precision guard that fails to discriminate**, so every rail admits roughly the same central pool of articles and the recency sort surfaces the 5 globally-newest clusters everywhere.

- **The fix that kills the symptom** (Stage 1): require a proper-noun anchor (title keyword *or* entity) for admission — semantic distance may only *rank*, never *admit alone*. Ships without any live data.
- **Two secondary items**: recalibrate the uncalibrated distance thresholds (Stage 2, needs data), and fix a separate latent topic-over-tagging bug (Stage 3 + Stage 4 data cleanup).
- **The load-bearing test gap**: nothing in the suite asserts two rails are disjoint. That is exactly why this shipped.

---

## 2. Symptom

From the on-device screenshots (Android, home screen):

- Rails headed "South Korea Stock Market", "UK Politics", "Russia Ukraine", "AI Supply Chain", "Cockroach Janta Party Protest".
- **Every** rail shows the identical body: *US/Tehran asylum data → Avatar Aang trailer → an Agra murder story (Hindi) → BMC shuts Mumbai schools → Jim Cramer market rotation*.
- Same stories, same order, on every rail. Uniform "9+ NEW" badge.
- The stories are unrelated to each other **and** to the rail header.

---

## 3. Root cause

### 3.1 The rails are `saved_search` follows

Typing free text on `/follow/new` always mints `kind="saved_search"` ([`follow/new/page.tsx:42`](../../frontend/src/app/follow/new/page.tsx)). The headers are verbatim the calibration phrases in [`scripts/measure_follow_distances.py:29`](../../backend/scripts/measure_follow_distances.py); "Cockroach Janta Party Protest" is typed junk. None of these exist as seeded `Topic` rows, so they dispatch to [`evaluate_saved_search`](../../backend/app/services/rails.py) (`rails.py:350`), **not** `evaluate_topic`/`evaluate_entity`.

### 3.2 The precision guard fails to discriminate — two faces of one defect

`evaluate_saved_search` runs a hybrid: a pgvector ANN semantic leg, a title-keyword leg, and an entity-alias leg, admitted by [`_admit`](../../backend/app/services/rails.py) (`rails.py:64`). It collapses in one of two ways depending only on whether embeddings are alive:

| Face | Enabling condition | Mechanism | Code |
|---|---|---|---|
| **A — Semantic over-admit** *(best fit for identical **order**)* | `rails_dist_tight=0.22` / `rails_dist_loose=0.35` are **uncalibrated guesses** — the config comment and the calibration script both state query↔document distances were never measured in this system. | If real query↔doc distances in this corpus are compressed, every phrase's ANN nearest-set converges on the same central clusters, all `< 0.22`, and the `dist < tight → admit alone` branch passes them for every phrase. | `_admit` (`rails.py:76`) |
| **B — Degraded fan-out** | Gemini embedding quota exhausted (routine on the free tier). | `emb=None` → `semantic_available=False` → guard degrades to `keyword_hit OR entity_hit`, and `_entity_leg` expands match keys on **every ≥3-char token** of the phrase, so generic words map to hot entities whose recent articles are the global-newest clusters. | `_admit` (`rails.py:72`), `_entity_leg` (`rails.py:178`) |

Both terminate at the same recency slice:

```python
ordered = sorted(cluster_ids, key=lambda cid: newest_ts, reverse=True)
top = ordered[: settings.rails_stories_per_follow]   # rails.py:361-366
```

→ the 5 globally-newest clusters, in the same order, on every rail.

### 3.3 Why "identical order across rails" is the decisive tell

Over-admission that merely *widened* each rail would produce **overlap**, not byte-identical order. Perfect identical order means each rail's admitted set already **contains the same newest-5 at the top** — i.e. the guard is admitting a phrase-independent central pool. That is the fingerprint of Face A (converged ANN set) and, secondarily, Face B (broad entity fan-out).

### 3.4 Confidently ruled out

Each was investigated and adversarially challenged:

- **Frontend** — [`FollowRails.tsx:148`](../../frontend/src/components/FollowRails.tsx) renders each `rail.stories` keyed by `follow_id`; no shared/aliased state, no cache on this path. Distinct headers + identical bodies (both read from the same per-rail object) proves the **payload already contained identical stories**.
- **Topic over-tagging** (`new_topic_max_similarity=0.6`) — a genuine latent bug, but it only feeds `evaluate_topic`, which `saved_search` rails never touch. Fixed separately in Stage 3 so it is not the next report.
- **Entity rails / clustering / dedupe / 60s cache** — all build strictly per-follow; `_dedupe_follows` keys on `value.lower()` (distinct headers never merge); `_cache` is keyed by `user_id` and stores the whole list. None can force set-equality.

---

## 4. Confirm which face (before choosing Stage-2 numbers)

The code already emits the evidence. Stage 1 fixes both faces, so this does **not** block the fix — but the Stage-2 threshold values depend on it.

1. **Grep prod logs for `rail_distance_histogram`** (`rails.py:204`):
   - Present, with `under_tight` ≈ `rails_ann_k` (50) for every phrase → **Face A** (miscalibration).
   - Absent → the semantic leg never ran → **Face B** (embeddings down).
2. **`GET /pipeline`** → `last_embedding_error` = `quota` / `auth` / `no_key` confirms Face B is active.
3. **Measure the real distribution** (optional, for Stage 2):
   ```bash
   cd backend
   GEMINI_API_KEY=… DATABASE_URL=postgresql+asyncpg://… python -m scripts.measure_follow_distances
   ```

> Note: the Supabase MCP connected to this workspace is a different app ("Plutus", personal finance), so prod NewsLens data is not reachable from the agent — these checks must be run against the Render deployment.

---

## 5. The fix

### Stage 1 — Harden the precision guard *(the actual bug fix; ships without live data)*

**Principle:** a cluster joins a `saved_search` rail only when a proper-noun anchor (title keyword **or** entity) confirms it. Semantic distance ranks; it never admits alone. This extends the design's existing intent for the `loose` tier to close the `tight` hole and the degraded fan-out.

#### 1a. `_admit` — remove anchor-free admission  ·  `rails.py:64`

```python
def _admit(dist, keyword_hit, entity_hit, *, semantic_available):
    anchor = keyword_hit or entity_hit
    if not semantic_available:
        return anchor                                   # degraded: proper-noun only (leg tightened in 1b)
    if dist is None:
        return False
    return dist < settings.rails_dist_loose and anchor  # semantic ran: proximity AND a proper-noun anchor
```

Deletes `if dist < settings.rails_dist_tight: return True`. Under Face A, the converged central set (Avatar, BMC, Cramer, …) has no keyword/entity overlap with "South Korea Stock Market" → not admitted → symptom dies. A genuine match ("US Iran war" → an Iran story) still passes: `< loose` **and** the token-entity leg confirms `iran`.

#### 1b. `_entity_leg` — full-phrase-only in degraded mode  ·  `rails.py:173`

Split the match keys so the per-token expansion is used **only as confirmation when the semantic leg ran**; the degraded path uses the full phrase only.

```python
async def _entity_leg(db, phrase, since, *, tokens=True):
    keys = {norm_company(phrase)}
    if tokens:
        keys |= {norm_company(tok) for tok in phrase.split()}
    keys = {k for k in keys if len(k) >= 3}
    ...
```

Call from `evaluate_saved_search` (`rails.py:153`) with `tokens=semantic_available`. Kills Face B's "any shared word → hot entity" fan-out while preserving token confirmation for healthy rails.

#### 1c. Bound the degraded candidate union  ·  `rails.py:159`

`kw_ids` and `ent_ids` are each capped at `rails_ann_k`, but their **union** is not. Sort the union by recency and slice to `rails_ann_k` before `_recent_cluster_of`, so a broad phrase can't fan out to thousands.

#### 1d. Honest-empty over confident-wrong  ·  `rails.py:349`

When the degraded path produces no keyword hit, `evaluate_saved_search` returns `set()` → the existing "Nothing new — we're watching" empty state ([`FollowRails.tsx:39`](../../frontend/src/components/FollowRails.tsx)) renders instead of the global newest-5. *(Product decision — see §9.)*

#### 1e. Collapse tripwire (observability)  ·  `rails.py:315`

In `rails_for_user`, after building, if ≥3 rails resolve to an identical top-cluster-id set, emit `logger.warning("rails_collapsed_identical", user_id=…, n_rails=…)`. Log-only — this is the missing telemetry that let the bug ship silently.

### Stage 2 — Recalibrate thresholds *(data-driven; needs §4 histogram)*

- From the measured query↔doc distribution, set `rails_dist_tight` just below the on-topic cluster and `rails_dist_loose` at the gap before the off-topic tail (`config.py:186-187`).
- **Optionally** reintroduce a pure-semantic tier, but gate it behind a **relative-separation** test: admit anchor-free only when the best match is both `< tight` and clearly separated from the candidate median. A flat converged band (Face A) then returns empty instead of collapsing. Add only if the data shows real anchor-free matches being lost.

### Stage 3 — Latent topic over-tagging *(separate defect, same PR)*

Not the cause of this symptom, but the same class of over-broad-threshold bug on the `topic` path; fix it before it surfaces as its own report.

- `config.py:250`: `new_topic_max_similarity: 0.6 → 0.30`. It is a doc↔doc cosine distance in the same space as clustering (`0.15`); "same topic" should sit above clustering but well below the `0.6` generic-news tail.
- `fetcher.py:118`: seed the topic vector from `topic.name` — **drop the `"News about "` prefix**, which drags every topic centroid toward a generic-news point. Biggest single quality win; narrows every topic's radius independent of the threshold.
- `fetcher.py:40` (`assign_topics`, embedding branch): collect all under-threshold `(topic_id, distance)`, sort ascending, and tag **only the nearest `topic_assign_max`** (new config, default 3). A structural cap makes over-tagging impossible even if the threshold later drifts.

### Stage 4 — Data cleanup migration *(for Stage 3 rows only)*

The `saved_search` collapse writes nothing — Stage 1 fixes it instantly, no migration. The `0.6` over-tags **do** persist in `article_topics`. Because dev is `create_all`-managed but **prod runs `alembic upgrade head`**, ship the cleanup as an idempotent Alembic data migration (`op.execute`):

```sql
-- semantic-pass over-tags sit above the new bar; relevance_score = 1 - distance is persisted (fetcher.py:61)
DELETE FROM article_topics
WHERE relevance_score IS NOT NULL
  AND relevance_score > 0.0            -- spare keyword rows (inserted at 0.0, fetcher.py:174)
  AND relevance_score < (1.0 - 0.30);  -- i.e. distance > 0.30, the new threshold
```

Keyword rows (`relevance_score = 0.0` / `NULL`) are precise word-boundary matches — leave them. Optional second statement: a window-function pass keeping the top-3 by `relevance_score` per `article_id` to enforce the cap retroactively.

---

## 6. Tests

The suite never asserts two rails are disjoint — the gap that let this ship.

**Integration** ([`tests/integration/test_rails.py`](../../backend/tests/integration/test_rails.py)):

- `test_two_saved_search_rails_are_disjoint_when_embeddings_down` — two unrelated phrases sharing a generic token, `embed_query_cached` monkeypatched → `None`, seeded recent clusters; **assert the two rails' cluster-id sets are not equal**. *(the headline regression)*
- `test_degraded_saved_search_prefers_empty_over_global` — phrase with no verbatim title hit + embeddings down → `total == 0` (locks 1d).
- `test_rails_collapse_guard_logs` — force ≥3 identical rails → assert the `rails_collapsed_identical` warning fires (locks 1e).

**Unit** ([`tests/unit/test_rails_admit.py`](../../backend/tests/unit/test_rails_admit.py) + new `test_rails_entity_leg.py`):

- Semantic-available candidate with **no** anchor is **not** admitted, even at `dist < 0.22` (locks 1a).
- `_entity_leg("AI Supply Chain", tokens=False)` returns only full-phrase-aliased entities, never `supply`/`chain`/`ai` (locks 1b).
- `test_single_word_saved_search_still_matches_entity_when_degraded` — "Iran" still matches (full phrase = the token), so single-word follows keep working while degraded.

**Topic tagging:**

- `assign_topics` tags at most `topic_assign_max`, nearest-first.
- An off-topic article beyond `0.30` is not tagged.
- The cleanup `DELETE` removes semantic over-tags but spares keyword rows (`0.0` / `NULL`).

---

## 7. Ship order

1. **Stage 1a–1b + the disjoint-rails regression test** — this alone kills the screenshot. Land first.
2. Stage 1c–1e hardening + observability.
3. Stage 3 topic fix + Stage 4 cleanup migration.
4. Stage 2 recalibration once the histogram data is in hand.

Steps 1–3 in one PR; Stage 2 as a fast follow.

---

## 8. Risks & rollback

- **Healthy (embeddings-up) rails:** behaviour unchanged except that admission now *requires* the anchor the `loose` tier already required — precision only tightens.
- **Deliberate trade-off:** a `saved_search` whose true matches are purely semantic with zero shared keyword/entity will show fewer/empty results until Stage 2 recalibration. An honest empty rail beats five identical wrong ones; it self-heals when embedding quota resets.
- **Entity rails (`kind=entity`):** untouched — they resolve a specific `entity_id` and never call `_entity_leg`.
- **Topic changes (Stage 3/4):** separate function and table write-path; the only cross-effect is tighter, more relevant topic-rail membership.
- **Rollback:** Stage 1/3 are pure code — revert restores prior behaviour. The Stage 4 migration is a `DELETE`; take a `pg_dump` of `article_topics` first. Deleted rows regenerate via `assign_topics`/`backfill_topic_articles` on the next pass, so re-tagging recovers them.

---

## 9. Open decisions

1. **Degraded-mode UX (1d):** show an honest **empty rail** *(recommended)* or keep guessing when embeddings are down?
2. **`new_topic_max_similarity`:** ship `0.30` now, or block Stage 3 on a measured doc↔topic histogram? *(The per-article cap makes `0.30` safe either way.)*
3. **Retroactive per-article cap in Stage 4:** run it now, or let stale over-tags age out of the 72h rail window naturally?

---

## Appendix A — Evidence map (file : line)

| Claim | Location |
|---|---|
| Free text → `saved_search` | `frontend/src/app/follow/new/page.tsx:42` |
| Rail headers = calibration phrases | `backend/scripts/measure_follow_distances.py:29` |
| Dispatch by kind | `backend/app/services/rails.py:349-354` |
| Precision guard | `backend/app/services/rails.py:64-80` |
| Pure-tight anchor-free admission (the hole) | `backend/app/services/rails.py:76` |
| Degraded fallback | `backend/app/services/rails.py:72`, `:158-159` |
| Per-token entity fan-out | `backend/app/services/rails.py:178` |
| Recency slice (identical order) | `backend/app/services/rails.py:361-366` |
| Thresholds uncalibrated (comment) | `backend/app/config.py:175-188` |
| Distance histogram logging | `backend/app/services/rails.py:204-217` |
| Frontend renders per-rail, keyed | `frontend/src/components/FollowRails.tsx:148-149` |
| Topic over-tag threshold | `backend/app/config.py:250` |
| Topic tagging (assign / backfill) | `backend/app/services/fetcher.py:49`, `:150` |
| Topic seed phrase | `backend/app/services/fetcher.py:118` |
| `relevance_score = 1 - distance` | `backend/app/services/fetcher.py:61` |

## Appendix B — Files touched by the fix

- `backend/app/config.py` — `new_topic_max_similarity`, new `topic_assign_max`; (Stage 2) `rails_dist_tight` / `rails_dist_loose`.
- `backend/app/services/rails.py` — `_admit`, `_entity_leg`, `evaluate_saved_search`, `rails_for_user`.
- `backend/app/services/fetcher.py` — `assign_topics` cap + topic-seed text.
- `backend/migrations/…` — new Alembic data migration (Stage 4 cleanup).
- `backend/tests/integration/test_rails.py`, `backend/tests/unit/test_rails_admit.py`, new `test_rails_entity_leg.py`.
