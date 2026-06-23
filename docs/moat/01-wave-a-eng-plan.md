# Wave A — Engineering Plan: Trustworthy Per-Persona Impact Engine

> Parent: [`00-PLAN.md`](00-PLAN.md). Spec of record: `IMPACT_ENGINE_SPEC.md` (handover).
> Goal: replace the flat free-text "WIIFM" lens with the spec's structured, validated, guarded
> impact engine — the product's wedge. Ships behind a flag.

## Eng-review hardening (accepted 2026-06-24)

1. **Full persona now** — keep watchlist/depth_pref/region/persona_version (§2).
2. **Fix the cache write-race now** — server-side JSONB merge, not read-modify-write (§2, §3.3).
3. **Pydantic + bounded retry is the contract** — provider structured-output is best-effort; `not_advice` stamped server-side; ≤2 generations per open (§1, §3.1, §3.3, §5).
4. Code-quality fixes folded in: typed `Dimensions` submodel, `\b`-anchored token matching, hype→regenerate (§1, §3.2).
5. Test gaps added (§6): retry-exhaustion paths, TTL via injectable clock, `?refresh`, persona_version invalidation, frontend ImpactCard + AgreementMeter regression.

## 0. What exists today (baseline)

| Concern | Current state | File |
|---|---|---|
| Impact output | flat `{headline, dimensions:[{key,label,body}]}` over finance/profession/policy/daily | `lenses.py:68-80` |
| Generation | `response_format={"type":"json_object"}`, best-effort `extract_json`, **no Pydantic** | `llm.py:115-119` |
| Persona | `User.profession` (free text) + `User.locale` only | `models.py:46-61` |
| Cache | `story_clusters.impact_json` JSONB, subkey `prof:{sha1(profession)[:12]}`, source-hash invalidation, no TTL | `lenses.py:120-156,187-189` |
| Guardrails | **none** (no-advice / groundedness / honesty / hype) | — |
| UI | renders `{label,body}` + headline; footer "AI-generated · personalised" | `ImpactCard.tsx:69-99` |
| Persona read | `_user_profession_locale()` → User id=1 | `routes.py:998-1002` |

**Design stance:** keep the JSONB-on-cluster cache and the 200+`unavailable` degradation contract
(both work and the frontend already handles them — minimal diff). Fix the *content*: structured
contract, real persona key, validation, guardrails. The spec's dedicated `story_impact` table and
202/503 states are noted as multi-user-future, not built now.

---

## 1. Output contract (`StoryImpact`)

New Pydantic models. **Minimal-diff placement:** append to the existing `app/schemas.py` under an
`# --- Impact (moat) ---` section (avoids converting `schemas.py` into a package).

```python
class Horizon(str, Enum):  now="now"; weeks="weeks"; quarter="quarter"; year_plus="year_plus"
class Confidence(str, Enum):  low="low"; medium="medium"; high="high"

class Evidence(BaseModel):
    claim: str
    source: str                                  # must match a provided source outlet

class Dimension(BaseModel):
    applicable: bool
    relevance: str = ""
    mechanism: str = ""
    watch_items: list[str] = Field(default_factory=list, max_length=4)
    horizon: Horizon = Horizon.year_plus
    confidence: Confidence = Confidence.low
    confidence_rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list, max_length=4)

class FinancialDimension(Dimension):
    not_advice: bool = True       # STAMPED server-side after validation, NOT model-generated

class PersonalRelevance(BaseModel):
    score: conint(ge=0, le=100)   # range enforced by Pydantic — provider schema can't (OpenAI ignores min/max)
    one_liner: str

class Dimensions(BaseModel):      # typed → the three dimensions are actually validated (not a loose dict)
    professional: Dimension
    financial: FinancialDimension
    civic: Dimension

class StoryImpact(BaseModel):
    cluster_id: str
    headline: str
    personal_relevance: PersonalRelevance
    dimensions: Dimensions
    caveats: str = ""
```

Score → UI band: 0–39 *Low* (ghost), 40–69 *Notable* (muted), 70–100 *High* (amber).

---

## 2. Data model + migration

New Alembic revision, `down_revision='f76aec9da324'` (the baseline). `alembic revision -m "wave-a persona"`.

**Extend `users`** (keep folding persona onto the single-user row; the spec's `user_persona` table is
the multi-user future form — out of scope now):

```python
op.add_column('users', sa.Column('interests', postgresql.ARRAY(sa.Text()), server_default='{}'))
op.add_column('users', sa.Column('watchlist', postgresql.JSONB(), server_default='[]'))   # [{type,value}]
op.add_column('users', sa.Column('region', sa.String(64), nullable=True))
op.add_column('users', sa.Column('depth_pref', sa.String(16), server_default='standard')) # brief|standard|expert
op.add_column('users', sa.Column('persona_version', sa.Integer(), server_default='1'))
```

(`interests` exist today as `user_preferences` topic rows; keep those as the weighting signal and
mirror the chosen interest *names* onto `users.interests` for the prompt, OR read them from
preferences at prompt time. Recommend: read from `user_preferences` at prompt time — no duplication.)

Mirror the same fields onto `models.py::User` and `ProfileOut`/`ProfileUpdate` (`schemas.py:181-191`).

**Cache key fix (the real bug):** today two readers with different interests/watchlist **share** a
cached impact because the subkey is profession-only. Replace `profession_hash` with a full
`persona_hash` and add a TTL:

```python
def persona_hash(p) -> str:   # p = assembled persona dict
    blob = json.dumps({k: p.get(k) for k in
        ("profession","seniority","industry","interests","watchlist","country","region",
         "depth_pref","persona_version")}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
```

Cache entry gains `generated_at`; `get_lens` treats an entry older than 24h as a miss (cheap TTL
without a new table; **use an injectable clock**, not `datetime.now`, so the TTL is testable). Keep
the existing `source_hash` invalidation.

**Write path (race fix — eng review):** `get_lens` today does a full read-modify-write of the JSONB
column (`lenses.py:138-155`), so two concurrent writes to different subkeys of the same cluster row
silently clobber each other. Replace with a **server-side merge** so writes are atomic per subkey:
`UPDATE story_clusters SET impact_json = COALESCE(impact_json,'{}'::jsonb) || :entry WHERE id=:id`
(or `SELECT … FOR UPDATE` on the cluster row). Applies to all four lens columns, not just impact.

---

## 3. Backend changes (file by file)

### 3.1 `llm.py` — best-effort structured output + a Pydantic-validated seam
**Enforcement strategy (eng review): Pydantic validation + bounded retry IS the contract; provider
structured-output is best-effort only.** Neither provider can fully enforce the contract — OpenAI
`json_schema` ignores `minimum/maximum` (so the 0–100 score is unenforced model-side) and dislikes
`const`; Gemini `response_schema` lacks `additionalProperties`/`const` and has limited enums. So do
NOT depend on a single shared strict schema.
- Add optional `response_schema` + `max_tokens` params to `generate()`/`_generate_openai`/`_generate_gemini` (distinct from the existing truthy `schema` flag other lenses use).
- OpenAI: `response_format={"type":"json_schema",…}` with a **loose** schema (no min/max/const) where it fits, else `json_object`. Gemini: `response_mime_type:"application/json"` (+ `response_schema` only where supported). Keep `extract_json` as the defensive parse.
- The **caller** (`lenses.impact`) does `StoryImpact.model_validate(...)` — the real guarantee. `not_advice` is **not** in the generation schema; it's stamped server-side post-validation.
- `max_tokens=900` for the impact call only (spec §8).

### 3.2 `services/impact_guardrails.py` — NEW (the §7 lints, pure functions → unit-testable)
```python
ADVICE_TOKENS = {"buy","sell","hold","short","allocate","overweight","underweight",
                 "you should","target price","price target","will rise","will fall"}
HYPE_TOKENS   = {"game-changer","game changer","revolutionary","massive"}

def lint_no_advice(fin: dict) -> list[str]      # returns violations in relevance|mechanism|watch_items
def lint_groundedness(impact, source_outlets)   # evidence[].source ∉ outlets → drop; numerics not in input → flag
def enforce_honesty(impact)                      # applicable:true + empty/generic relevance → applicable:false
def detect_hype(impact) -> list[str]             # hype present → trigger regenerate (NOT raw word-deletion)
```

**Token matching (eng review):** match on `\b`-anchored regex, never substring `in` — "hold"/"short"
must not fire on *household*/*shareholder*/*shortage*/*shortly*. Hype detection triggers a regenerate
within budget (or neutral-synonym replace); never delete words mid-sentence (mangles prose).

### 3.3 `lenses.py` — rewrite `impact()` + new prompt
- Replace `_prompt_impact` (`:68-80`) with the spec's verbatim **system prompt + 7 HARD RULES +
  `<persona>/<story>/<sources>` user template** (spec §5). The money dimension prompt explicitly
  forbids advice.
- `impact()` flow — **one bounded retry budget: ≤2 generations total**, precedence validate→lint:
  assemble persona → `persona_hash` → cache lookup (TTL) → on miss: generate →
  `StoryImpact.model_validate()` (on failure regenerate **iff** budget remains) → **stamp
  `financial.not_advice=True`** → run §7 lints (no-advice / groundedness / honesty / hype) → if a
  lint fails and budget remains, regenerate once stricter; if it still fails, **fail safe**: set
  `financial.applicable=false` + drop offending evidence → **JSONB-merge** the validated+linted
  payload (race fix) → return.
- Keep the `profession_unset` short-circuit (`:183-184`) and the `unavailable` degradation.
- `source_outlets` for the groundedness lint = distinct `article.source.name` of the cluster.

### 3.4 `routes.py` — persona assembly + refresh
- `_user_profession_locale` → broaden to `_user_persona(db)` returning the full persona dict
  (profession, locale→country/region, interests from `user_preferences`, watchlist, depth_pref,
  persona_version). Impact route (`:1129-1134`) passes the dict.
- Add `?refresh=1` (maps to `get_lens(force=True)` — already supported internally `:128`).
- `/profile` PUT bumps `users.persona_version` on any persona change (lazy cache invalidation).

### 3.5 Config / flag
`config.py`: add `impact_v2_enabled: bool = True`. `lenses.impact()` branches old vs new on the flag
so rollout/rollback is one env var.

---

## 4. Frontend changes

| File | Change |
|---|---|
| `lib/api.ts:299-319` | Add typed `StoryImpact` interfaces (replace loose `LensResult` for impact); `getClusterImpact` returns `StoryImpact \| Unavailable` |
| `ui/ImpactCard.tsx:69-99` | Render: **relevance chip** (`{score} · HIGH/NOTABLE/LOW FOR YOU`, amber band), per-dimension **horizon + confidence** chips, **watch_items**, and the **"Not financial advice — exposure & signals only"** disclaimer on the financial dimension (replaces the generic footer `:97`). Hide dimensions with `applicable:false`. |
| `DeepDiveView.tsx:142-166` | Add the italic-serif **"so what" lead sentence** (`personal_relevance.one_liner`) + relevance/horizon chip above the fold (A7) |
| `ui/AgreementMeter.tsx:12-19` | **A6:** stop printing "Sources agree {pct}%" off the coherence float — relabel to "cluster coherence" (honest) until the real consensus metric lands in Wave B |

---

## 5. Error & rescue map (impact codepath)

All retries draw from **one shared budget: ≤2 generations per open** (validate-fail and lint-fail
share it; precedence validate→lint). No `except Exception` swallow — `get_lens` logs + returns typed
unavailable (`lenses.py:147-149`); the branches below sit above it.

| What can go wrong | Rescue | User sees |
|---|---|---|
| No key / provider down | catch `LLMUnavailable` → `{unavailable, reason:"no_llm_key"}` (200) | "Impact unavailable — add a key" (existing) |
| Model returns non-schema JSON | `model_validate` raises → regenerate **within budget** → still fails → `{unavailable, reason:"impact_invalid"}` | graceful hide |
| `lint_no_advice` violation | regenerate stricter **within budget** → else `financial.applicable=false` | money axis omitted, never advice |
| JSONB write race | server-side `||` merge (no read-modify-write) | — (no lost cache entry) |
| `lint_groundedness` finds bad source | drop that `evidence[]` entry | silently cleaned |
| Empty cluster / no sources | existing `{unavailable, reason:"no_sources"}` | hide |
| Profession unset | existing `{unavailable, reason:"profession_unset"}` | "Personalize → set profession" (existing) |

No `except Exception` swallow: `lenses.get_lens` already logs+returns typed unavailable (`:147-149`); keep that, add the validation/lint branches above it.

---

## 6. Test plan — fixing the "fake_llm can't test guardrails" gap

The integration `fake_llm` (`tests/integration/conftest.py:75-182`) returns canned JSON, so it
cannot exercise content guardrails. Two-pronged fix:

**A. Pure unit tests on the lints** (`tests/unit/test_impact_guardrails.py` — NEW, no LLM, fast):
- `lint_no_advice`: feed financial dimensions containing each ADVICE_TOKEN → assert all caught; clean text → no violation. *(covers Wave A acceptance: no-advice on a 50-case set — parametrize the 50.)*
- `lint_groundedness`: evidence source not in provided outlets → dropped; number absent from input → flagged. *(0-fabrication audit.)*
- `enforce_honesty`: `applicable:true`+empty relevance → flipped to `false`.
- `detect_hype`: each HYPE_TOKEN flagged; **false-positive guard** — *household / shareholder / shortage / shortly* must NOT fire.
- `StoryImpact.model_validate`: valid passes; **score 101 / -1 → rejected** (range is Pydantic's job, not the provider schema's); malformed/missing dimension → raises. *(100% schema-valid.)*

**B. Adversarial integration tests** (`tests/integration/test_impact_v2.py` — NEW):
- Add a `fake_llm_adversarial` fixture that returns an impact dict laced with advice ("you should buy"), a fabricated source, and a hype token → assert the endpoint response has advice neutralized, bad evidence dropped, hype gone, `financial.not_advice==true`.
- **Persona distinctness:** seed two personas (e.g. "nurse" vs "trader" with different interests) → assert two distinct cache entries (`persona_hash` differs) and both trigger generate (not collapsed to one). *(persona-sensitivity, testable without varying LLM output.)*
- **Prompt-builder unit** (`tests/unit/test_impact_prompt.py`): assert the new user template embeds profession, interests, watchlist, region (deterministic — proves personalization is wired even though `fake_llm` is canned).
- **TTL:** inject clock / set `generated_at` 25h ago → assert cache miss + regenerate.
- **Retry exhaustion (validate):** fake_llm returns invalid JSON twice → `{unavailable, reason:"impact_invalid"}`, exactly 2 generate calls.
- **Retry exhaustion (lint):** fake_llm returns advice twice → response has `financial.applicable=false`, exactly 2 generate calls.
- **`?refresh=1`:** bypasses a fresh cache entry and regenerates.
- **persona_version invalidation:** PUT `/profile` (any persona change) → next impact is a cache miss.
- **Graceful degradation:** keep the existing `test_impact_graceful_when_llm_fails` (real seam → unavailable, never 500).

**C. Frontend (vitest):**
- `ImpactCard`: renders score band (Low/Notable/High), per-dimension horizon+confidence, watch_items, the "Not financial advice" disclaimer on the financial axis; **hides `applicable:false` dimensions**.
- `AgreementMeter` **regression (CRITICAL):** asserts it no longer renders "Sources agree" (existing user-visible behavior changes — Iron Rule).

All integration tests run in Docker per the harness header (`tests/integration/conftest.py:1-11`).

---

## 7. Rollout

1. Migration: `alembic upgrade head` (additive columns only — backward-compatible, no locks on a single-user DB).
2. Ship behind `impact_v2_enabled` (default on; flip off to revert to the old lens instantly).
3. Old `impact_json` cache entries (subkey `prof:*`) are simply ignored by the new `persona_hash` keys — no data migration; they age out.
4. Verify: `/clusters/{id}/impact` returns a `StoryImpact` for a set profession; money axis shows the disclaimer; no-advice lint test green; persona-distinctness test green.

---

## NOT in scope (this wave)

- **`story_impact` table / 202·503 states** — keep JSONB-on-cluster + 200·`unavailable` (deferred to multi-user).
- **Real consensus/divergence metric** — Wave A only makes `AgreementMeter` *honest*; the actual concur/dissent metric is Wave B (B3).
- **Depth toggle behavior** — `depth_pref` column lands now, but the generalist↔expert prompt switch is Wave B (B5).
- **Entity-impact from watchlist** — `watchlist` column lands now; "everything affecting X" is a later wave.
- **GraphRAG / deeper retrieval** — Wave D.

## 8. Implementation checklist (ordered)

- [ ] Migration: full persona columns on `users` (watchlist, depth_pref, region, persona_version) + mirror on `models.py::User`, `ProfileOut/Update`
- [ ] `schemas.py`: typed `Dimension`/`FinancialDimension`/`Dimensions`/`StoryImpact` + a **loose** generation schema (no min/max/const)
- [ ] `llm.py`: optional `response_schema` (best-effort) + `max_tokens` passthrough; keep `extract_json` fallback
- [ ] `impact_guardrails.py` (NEW, `\b`-regex tokens) + `tests/unit/test_impact_guardrails.py`
- [ ] `lenses.py`: spec prompt, full `persona_hash`, stamp `not_advice`, validate→lint with **≤2-gen budget**, **JSONB-merge writes**, injectable-clock TTL
- [ ] `routes.py`: `_user_persona`, `?refresh=1`, persona_version bump on profile PUT
- [ ] `config.py`: `impact_v2_enabled`
- [ ] Frontend: `api.ts` types, `ImpactCard` (score band/horizon/confidence/watch/disclaimer, hide `applicable:false`), `DeepDiveView` lead sentence, `AgreementMeter` honest relabel
- [ ] `tests/integration/test_impact_v2.py` (adversarial fake_llm, persona distinctness, TTL, **both retry-exhaustion paths**, `?refresh`, persona_version invalidation)
- [ ] `tests/unit/test_impact_prompt.py` + frontend vitest (`ImpactCard`, `AgreementMeter` regression)
- [ ] Run: `docker compose run --rm backend python -m pytest tests -q` + `cd frontend && npx vitest run`

## 9. UI design spec (Wave A) — from design review

Calibrated to `design-system.md` + the v4 mock. Three design decisions (2026-06-24): lead falls
back to the AI-summary's first sentence when impact is unavailable; low-relevance (score 0–39) shows
a **dimmed** card (not hidden); Wave A keeps the **interim** layout (lead+chip under title, ImpactCard
expanded in place — the v4 collapsed accordion is Wave B4).

**Information hierarchy (Deep Dive, Wave A interim):**
```
1  Title                         Instrument Serif italic, hero 28px            ← what
2  Lead "so what" sentence       Serif italic ~20px, --text-primary,           ← THE so-what
                                 2px --accent left border (mirrors v4 .lead)      (one_liner; else AI-summary sentence 1)
3  Relevance chip + horizon chip mono 11px, band by score (see tokens)         ← how much it matters to you
4  AgreementMeter                honest "cluster coherence" (no "agree")        ← trust
5  AI Summary box                existing (violet --drill)                     ← detail
6  ImpactCard "WHAT'S IN IT FOR ME"  expanded card, --accent-subtle            ← per-persona detail
7  SourceSpectrum + Source cards existing (free-first)                         ← provenance
8  StrategicCard / TriviaCard    existing
```

**Interaction states (impact surface):**
| State | What the user sees |
|---|---|
| loading | existing skeleton (`skeleton h-24`) |
| profession_unset | existing "Personalize → set your profession" invite (`--accent-subtle`) |
| no-key / generating / llm_error | card hidden (graceful); **lead falls back to AI-summary sentence 1** |
| **low relevance (0–39)** | card + chip in **ghost** band (`--text-ghost`), one-liner e.g. "Low relevance to your work" |
| notable (40–69) | **muted** band (`--text-secondary` / `--text-muted`) |
| high (70–100) | **amber** band (`--accent` on `--accent-subtle`, `--accent-muted` border) |
| `applicable:false` dimension | dimension omitted from the card |

**Token mapping (no new colors):**
- Relevance band: High→`--accent`/`--accent-subtle`/`--accent-muted`; Notable→`--text-secondary`; Low→`--text-ghost`.
- Confidence dot (mock `cd hi/me/lo`): high→`--agree`, medium→`--accent`, low→`--text-ghost`.
- Horizon chip: mono 11px, `--surface-raised` bg, `--text-secondary`.
- "Not financial advice — exposure & signals only": mono 10px `--text-ghost`, **always visible** under the financial dimension (mirrors the AI-summary disclaimer pattern, design-system §AI Summary Box).
- AgreementMeter: label → "cluster coherence" (mono), keep the bar + tier colors; remove the word "agree".

**Responsive (320px):** chips wrap; relevance+horizon stack below ~340px; lead 18px (from 20). Reuse design-system 320 overrides.

**Accessibility:**
- **Non-color indicators (design-system rule):** every chip shows its value as text — score "82", band word "HIGH/NOTABLE/LOW", "WEEKS", confidence "MED" — never color alone.
- Contrast: `--accent` on `--accent-subtle` ✓ (accent-on-surface 5.2:1 per design-system).
- ImpactCard: `role="complementary" aria-label="What this means for you"`; dimensions as `<dl>` (already).
- **Reduced motion:** guard the ImpactCard framer-motion entrance (`y:8→0`) behind `prefers-reduced-motion` — no transform when set (design-system §Reduced Motion).

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | done | re-sequenced around the moat; profession-agnostic positioning locked |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | issues resolved | 9 findings (1 critical: JSONB write-race); 3 forks decided; all folded in |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | issues resolved | 5/10 → 9/10; 3 decisions (lead fallback · dimmed low-relevance · interim layout); §9 spec added |
| Outside Voice | codex | Independent 2nd opinion | 0 | — | skipped (codex unavailable in this env) |

**UNRESOLVED:** 0 — eng forks (full persona · fix race · Pydantic+retry) + design forks all answered.
**VERDICT:** CEO + ENG + DESIGN cleared — ready to implement.
