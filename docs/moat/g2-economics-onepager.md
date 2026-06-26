# G2 economics — the N* break-even (Gate-2 deliverable)

The GraphRAG investment only pays off above a user count where the **one-time, content-cost**
extraction amortizes across enough users versus the **per-user** vector baseline.

```
N*  =  extraction_cost_per_day  /  vector_baseline_cost_per_user_per_day
```

- **extraction_cost_per_day** — the G1 entity-extraction LLM spend: one JSON pass per *settled,
  changed* cluster (not per article, not per tick), on the platform key, cheap model. From real
  ingest: `clusters_extracted_per_day × tokens_per_cluster × $/token`.
- **vector_baseline_cost_per_user_per_day** — what a pure pgvector retrieval (no graph) costs to
  serve one active user per day.

**Interpretation:** below N* users, the graph is a cost with no offsetting scale; above it, the
shared global graph (extracted once) is cheaper per marginal user than re-running vector retrieval
for each. G1 keeps the **numerator low** (extract-once, on-change, salient-only) so N* lands low.

**Status:** this is a *paper* deliverable to evaluate before committing to G3 (the multi-hop engine).
G2's overlay adds **zero** new extraction (it only JOINs the existing global graph per user), so it
does not move the numerator. Plug in real token/ingest numbers when WAU exists; until then the gate
(~50–100 WAU + ≥15–20% multi-hop demand) is unmet and G3 stays deferred.
