# NewsLens — Copy Guidelines & Review Process

The single standard for every word a user can read in NewsLens: screen copy, button labels,
empty states, errors, notifications, store listings, onboarding.

**Why this exists:** internal jargon leaked into the UI (`src:7 · coh:0.88`, "OpenAI API key for
embeddings…"). Readers don't know what coherence or an embedding is. This guide + the automated
guard (`npm run lint:copy`) + the review checklist make sure it never ships again.

Machine-readable companion: [`terminology.json`](./terminology.json) — the guard reads `banned`,
this guide explains the `glossary`.

---

## 1. Brand voice

NewsLens is **calm, credible, and editorial** — a smart desk editor, not a hype machine and not a
lab notebook. It serves any profession (doctor, PM, trader, geopolitics geek), so copy is
**plain and universal**, never insider.

| We are | We are not |
|---|---|
| Clear, plain, confident | Jargon-y, clever-for-its-own-sake |
| Calm and editorial | Clickbait, breathless, ALL-CAPS hype |
| Trust-forward (sources, agreement) | Vague ("trust us") |
| Concise | Padded, hedge-heavy |
| Neutral on the news itself | Editorialising the story's politics |

**Voice test:** would this read naturally in a quality newspaper's product, to a smart reader who
is *not* an engineer? If not, rewrite.

## 2. Plain language — the core rule

> Never expose how the sausage is made. Show the value, hide the pipeline.

Every internal term has a user-facing translation. The full map is in
[`terminology.json`](./terminology.json) → `glossary`. The essentials:

| Internal (code/DB/ML) | Show the user |
|---|---|
| `src:N` / source_count | **N sources** |
| `coh:0.88` / coherence | **88% agreement** (tiered colour, see §4) |
| "High confidence" (legacy) | **agreement** — standardise the word |
| cluster / story_cluster | **story** |
| embedding / pgvector | *(hidden)* — say the benefit: "find related stories" |
| explore/exploit mix | **Your topics** / **Discover new** |
| GDELT, RSS, trafilatura, asyncpg, Fernet, dedup, backfill | *(never surface)* |
| embedding_status = pending | *(hidden)* — show the snippet instead |

## 3. Numbers

- **Percentages, not decimals.** `0.88` → **88%**. Round to whole numbers in UI.
- **Spell the unit in words** where space allows: `88% agreement`, `7 sources`, `3 min read`.
- Counts get a real noun and pluralise: `1 source` / `7 sources`.
- No false precision — `~100k`, not `103,412`, unless the exact figure is the point.

## 4. The trust signal (sources + agreement)

The most jargon-prone surface. Standard treatment:

- **Sources** — neutral pill: `7 sources`.
- **Agreement** — colour-coded by tier (this is the *only* place colour encodes a value):
  - **≥ 80%** → green · "high agreement"
  - **60–79%** → amber · "moderate"
  - **< 60%** → grey · "mixed / developing"
- **Wording honesty:** coherence is a similarity score, so "agreement" / "consensus" is a fair
  plain-English translation — never imply a literal vote ("88% of sources voted").

## 5. Theme & discipline

- **Sentence case** for sentences and buttons ("Read full article"). `UPPERCASE` mono is reserved
  for the established label style (section kickers like `TOP STORIES`, data tags) — that's a
  *design* convention, not prose; don't uppercase sentences.
- **Consistent terms:** one concept = one word, everywhere. A "story" is always a story (never
  also "cluster" or "article group"). Add new terms to the glossary before using them.
- **Verbs for actions** ("Save", "Read full article"), **nouns for things** ("Briefing", "Sources").
- **Errors** are calm and actionable, never raw: not "500: cluster not found" → "We couldn't load
  this story. Pull to refresh."
- **No leaking secrets/IDs** in copy — never show internal IDs, keys (mask them), or stack traces.

## 6. Do / Don't

| Don't | Do |
|---|---|
| `src:7 · coh:0.88` | `7 sources` · `88% agreement` |
| "OpenAI API key for embeddings and summaries" | "Powers AI summaries and related-story matching" |
| "High confidence ●●●○" | "88% agreement" (green) |
| "No clusters found" | "No stories yet — check back soon" |
| "Embedding pending" | *(show the article snippet)* |
| "Explore ratio: 0.3" | *(hidden — it just tunes the mix)* |

---

## 7. Review process

Copy is reviewed **every time it changes**, at three gates:

1. **Author self-check** — writer runs the checklist (§8) before opening a PR.
2. **Automated guard (blocking)** — `npm run lint:copy` runs locally and in CI. `error`-level
   jargon fails the build. Run it as part of standard validation (see root `CLAUDE.md`).
3. **Human copy review** — the reviewer confirms the checklist on the PR. Anything user-visible
   (screens, emails, push, store text) needs a copy ✓ in review, same as a code ✓.

New user-facing term? → add it to [`terminology.json`](./terminology.json) (glossary, and `banned`
if its internal form must never ship) **in the same PR**.

## 8. Copy review checklist

Paste into the PR description for any change touching user-visible text:

```
Copy review
- [ ] No internal jargon (ran `npm run lint:copy`, 0 errors)
- [ ] Numbers are %/rounded; units spelled out where space allows
- [ ] One concept = one word; matches terminology.json glossary
- [ ] Sentence case for prose/buttons; UPPERCASE only for label style
- [ ] Errors are calm + actionable; no raw codes/IDs/keys
- [ ] Reads naturally to a non-engineer (voice test)
- [ ] New terms added to terminology.json
```

## 9. The guard

`frontend/scripts/check-copy.mjs` scans `frontend/src/**/*.{ts,tsx}` for `banned` entries:

- `pattern` (e.g. `src:`, `coh:`) → flagged anywhere.
- `word` with `scope: "string"` → flagged inside quoted strings / JSX text (skips imports & types).
- `word` with `scope: "jsx-text"` → flagged only in visible JSX text (lower-confidence, `warn`).

`error` severity exits non-zero (fails CI); `warn` prints advisories. Run: `npm run lint:copy`.
