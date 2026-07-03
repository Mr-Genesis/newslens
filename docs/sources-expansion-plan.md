# NewsLens Source Expansion — Final Plan (for approval)

> **STATUS — SHIPPED (all three phases merged to master).** This document is the record of intent; the plan below was executed largely as written.
> - **Phase 1 — Seed + gate** → **PR #77.** `research`/`expert` enum + 6 nullable `sources` columns (migration `b2c3d4e5f6a7`); `audience.py` persona gate (feed floor 55, briefing floor 70); `_upsert_sources` admin-lock + `per_fetch_cap` + `_best_body` fetcher fixes; expert-score validation on `POST /admin/sources`. `sources.json` is a 117-source union (45 gated).
> - **Phase 2 — Badges + ranking + opt-in** → **PR #84.** `SourceTierBadge` (RESEARCH/EXPERT/PREPRINT) on StoryCard/SourceCard/DiscoverCard; feed-rank credibility multiplier ×[0.9, 1.1]; briefing +0.15 story-weight bonus; follow-source (`follows.kind="source"`); discover deck reserves up to 5 gated cards; `GET /feed?source_type=` filter + `getFeed(sourceType)` client.
> - **Phase 3 — Credibility ops + personal research feeds** → **PR #91** (backend-only, no new migration). `PUT /admin/sources/{id}/credibility` (apply + lock); monthly propose-only LLM review (`credibility.py`); weekly PubMed E-utilities adapter (`pubmed.py`) + arXiv-by-interest generator (`arxiv_gen.py`); LLM profession→tags fallback (`resolve_tags`); research clusters extract entities at 1 source. Three new APScheduler crons in `main.py`.
> - **DEFERRED (not shipped):** the §5.5/Phase-2 feed filter **chip UI** — the `?source_type=` API and `getFeed(sourceType)` client shipped, but there is no rendered `/feed` screen to host the chips yet.

**Date:** 2026-07-03 · **Scope:** 3 new source tiers on top of the current 39 seeds · **Verification standard:** every proposed feed was fetched live with `curl --max-time 25 -A "NewsLens/0.1 (RSS Reader)"`; VERIFIED = HTTP 200 + XML/RSS/Atom marker in first 2KB (freshness spot-checked; identity confirmed via feed `<title>` for all Substacks). Unverified feeds are in Appendix A, not the seed list.

---

## 1. Executive Summary

| Tier | source_type | Verified / proposed | In Phase-1 seed | Examples |
|---|---|---|---|---|
| Research papers | `research` (**new enum value**) | 19 RSS feeds verified + 1 API mechanism (PubMed E-utilities) verified; 7 candidates failed/stale | 19 | arXiv cs.AI, medRxiv, NEJM, JAMA, Nature, PLOS ONE, Quanta |
| Expert blogs | `expert` (**new enum value**) | 26 verified (+10 verified spares held in reserve) | 26 | Ground Truths (Eric Topol, 95), One Useful Thing (Ethan Mollick, 92), Marginal Revolution (90), Stratechery (82) |
| News channels | existing types | 35 verified; 8 dead candidates replaced with working alternates | 35 | Reuters (via proxy), DW, FT, Bloomberg, Nikkei Asia, Deccan Herald, Bar & Bench, ESPNcricinfo |
| **Total** | | **80 verified** | **80** | roughly 3x the current catalog |

**The three product rules this plan enforces:**
1. **Research and expert content is persona-gated** — a doctor sees NEJM; a lawyer never does (unless they follow it). News tiers are untouched for everyone.
2. **Expert admission is allowlist-only with a human-owned credibility score** (0–100 rubric, rationale on record). LLM review can *propose* score changes, never apply them.
3. **Preprints are labeled** (`PREPRINT · not peer-reviewed`) — non-negotiable for medical content.

Credibility scores below are normalized to one 0–100 scale (research/news sub-team scores were 0–1; multiplied by 100).

---

## 2. Tier 1 — Research Papers (`source_type: "research"`)

### 2.1 Verified feeds by profession

**Medicine (5 + PubMed mechanism)**

| Source | Feed | Cred | Paywalled | Notes |
|---|---|---|---|---|
| NEJM Current Issue | `nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss` | 98 | yes | Weekly TOC, 65 items. Descriptions are citation-only ("Volume 395, Issue 1…") — thin snippets, enrich downstream |
| The Lancet | `thelancet.com/rssfeed/lancet_current.xml` | 98 | yes | Usable summary prose. Contains non-UTF8 bytes — sanitize on ingest |
| JAMA | `jamanetwork.com/rss/site_3/67.xml` | 97 | yes | Real abstract prose — good snippets. Sibling `site_N/NN.xml` specialty feeds (Cardiology, Oncology…) available for expansion |
| Nature Medicine | `nature.com/nm.rss` | 95 | yes | Low volume (~9 items), curated. `nature.com/<jrnl>.rss` pattern generalizes |
| medRxiv (all) | `connect.medrxiv.org/medrxiv_xml.php?subject=all` | 70 | no | **PREPRINT.** Full abstracts in-feed. Per-specialty variants: `?subject=cardiovascular_medicine`, `?subject=oncology`, etc. |

**AI / CS / Engineering (5)**

| Source | Feed | Cred | Notes |
|---|---|---|---|
| arXiv cs.AI | `rss.arxiv.org/rss/cs.AI` | 80 | **PREPRINT.** ~353 items/day — full abstracts in `<description>`, excellent snippets, **cap mandatory** |
| arXiv cs.LG | `rss.arxiv.org/rss/cs.LG` | 80 | **PREPRINT.** ~273/day, same caveats |
| IEEE Spectrum | `spectrum.ieee.org/feeds/feed.rss` | 85 | Engineering journalism (magazine), not primary papers — research-adjacent |
| ACM TechNews | `technews.acm.org/rss/technews.xml` | 82 | Curated CS digest; links out — dedupe against tech news sources |
| *(pattern)* arXiv any category | `rss.arxiv.org/rss/<CATEGORY>` | — | Verified with cs.CL. The app can mint a feed per user interest (cs.CV, stat.ML, eess.*, math.*) — Phase-3 generator |

**Economics / Finance (2)**

| Source | Feed | Cred | Notes |
|---|---|---|---|
| arXiv econ.GN | `rss.arxiv.org/rss/econ.GN` | 75 | **PREPRINT.** ~12/day, manageable |
| arXiv q-fin | `rss.arxiv.org/rss/q-fin` | 75 | **PREPRINT.** ~21/day, covers trading/risk/portfolio subfields |

(NBER, SSRN, VoxEU all failed verification — Appendix A. Econ persona is covered by arXiv + the expert tier for now.)

**General science / biology (7)**

| Source | Feed | Cred | Paywalled | Notes |
|---|---|---|---|---|
| Nature (flagship) | `nature.com/nature.rss` | 98 | yes | 76 items, research + news mixed. Distinct URL from existing "Nature News" seed — both persist; consider a dedup pass |
| Science eTOC | `science.org/action/showFeed?type=etoc&feed=rss&jc=science` | 98 | yes | Peer-reviewed TOC; citation-thin descriptions |
| Science News (AAAS) | `science.org/rss/news_current.xml` | 90 | no | Free newsroom prose — good snippets |
| PNAS | `pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas` | 93 | no | 88 items; citation-thin descriptions |
| PLOS ONE | `journals.plos.org/plosone/feed/atom` | 85 | no | Fully OA — full text ingestible. `journals.plos.org/<slug>/feed/atom` generalizes to PLOS Medicine etc. |
| bioRxiv (all) | `connect.biorxiv.org/biorxiv_xml.php?subject=all` | 72 | no | **PREPRINT.** Full abstracts; per-subject variants |
| Quanta Magazine | `quantamagazine.org/feed/` | 88 | no | Low volume, high quality science journalism |

**Aggregator (1):** ScienceDaily `sciencedaily.com/rss/all.xml` (cred 60 — press-release aggregator; **below briefing floor by design**, feed/discover only; per-topic feeds at `/rss/<topic>.xml`).

### 2.2 Ingestion caveats (all confirmed by live fetches)

- **Snippet quality is bimodal.** STRONG in-feed abstracts: all arXiv, medRxiv, bioRxiv, JAMA, PLOS, Quanta, Lancet. THIN citation-only: NEJM, PNAS, Science eTOC — for these, fetch abstract via DOI landing page or let the summarizer enrich, else cards render near-empty.
- **Preprint labeling is a hard product requirement.** arXiv/medRxiv/bioRxiv get `is_preprint: true` at source level (these feeds are 100% preprints — no per-article detection needed). medRxiv is clinically safety-sensitive; never render as established guidance.
- **Paywall flags:** `is_paywalled: true` on NEJM, Lancet, JAMA, Nature Medicine, Nature, Science eTOC (abstracts free, full text gated — free-first sort and DOI deep-links apply). Everything else in the tier is `false`.
- **Volume:** arXiv cs.AI + cs.LG alone emit ~600 items/day — more than the entire current pipeline. `per_fetch_cap: 25` on all research feeds is mandatory (first fetch otherwise ingests the full backlog into the Gemini embedding queue).
- **Encoding:** Lancet/medRxiv carry non-UTF8 bytes and HTML entities — sanitize before embedding.

### 2.3 The per-specialty PubMed pattern (Phase 3)

Two mechanisms exist; only one works programmatically:

- **VERIFIED — E-utilities pipeline:** `esearch.fcgi?db=pubmed&term=<specialty>&reldate=7&datetype=edat` returned 200 JSON (1,365 hits for "cardiology") → `efetch.fcgi?db=pubmed&id=<PMID>&rettype=abstract&retmode=xml` returned structured `<AbstractText>`. **This is how NewsLens should generate a personal research feed per doctor:** map `user.profession` → MeSH/free-text term → weekly esearch → efetch abstracts, via a small XML→internal-feed adapter (not drop-in RSS). Needs an NCBI api_key and ≤3 req/s.
- **UNVERIFIED — literal PubMed RSS** (`pubmed.ncbi.nlm.nih.gov/rss/search/<GUID>/`): the GUID must be minted by the logged-in UI "Create RSS" button; scripted attempts returned 403 (CSRF/session-gated) and synthetic keys 500. **Do not build on this.**

---

## 3. Tier 2 — Expert Blogs (`source_type: "expert"`)

### 3.1 The scoring rubric (0–100, hand-applied at seed)

| Component | Weight | Signals |
|---|---|---|
| Affiliation / institutional role | 30 | professor/researcher at named institution; senior operator; independence disclosure |
| Education / domain credentials | 20 | degrees, board certification, publication record |
| Track record / mainstream citation | 25 | years publishing, books, cited by major outlets, correction history |
| Audience scale | 15 | subscriber/follower counts — **proxy only, ±3** |
| Original analysis vs aggregation | 10 | own research/data vs link-blogging |

**Bands:** 90+ canonical authority · 75–89 established expert · 60–74 credible practitioner · **55–59 feed-eligible but never in briefing** · **<55 discover-only** (or not admitted). Honesty note: scores come from model knowledge (cutoff Jan 2026), not live lookups; audience sub-scores are estimates. **Four scores are explicitly lower-confidence: Zvi (54), Apricitas (57), Technopolitik (64), Mostly Economics (56).** Anonymous authors (e.g. Doomberg) are excluded outright — unscorable identity is exactly the owner's "can't just mention anyone" constraint. Matt Levine excluded (no public RSS).

### 3.2 Verified list (26 — all HTTP 200 + XML + feed-title identity check)

**Tech / AI (10)**

| Source | Author | Score | Rationale (one line) | Paywalled |
|---|---|---|---|---|
| Stratechery | Ben Thompson | 82 | Aggregation Theory is industry canon; Kellogg MBA; public feed = free weeklies only | yes |
| One Useful Thing | Ethan Mollick | 92 | Wharton professor, MIT PhD; most-cited academic voice on AI-at-work | no |
| AI as Normal Technology | Narayanan & Kapoor | 88 | Princeton CS professor + researcher; "AI Snake Oil" book; feed renamed live, same URL | no |
| Interconnects | Nathan Lambert | 79 | AI2 research scientist, Berkeley PhD, ex-HuggingFace RLHF lead | no |
| Import AI | Jack Clark | 78 | Anthropic co-founder, ex-OpenAI policy; congressional testimony. **Add Substack feed only — jack-clark.net mirror would self-cluster** | no |
| Benedict Evans | Benedict Evans | 76 | Ex-a16z partner; annual macro-trends deck is an industry staple | no |
| SemiAnalysis | Dylan Patel | 76 | Semiconductor research firm cited by WSJ/Bloomberg; no formal credential (flagged) | yes |
| Simon Willison's Weblog | Simon Willison | 73 | Django co-creator; de-facto practical LLM-engineering reference. High volume — cap 10 | no |
| The Pragmatic Engineer | Gergely Orosz | 72 | #1 tech Substack (>900k), ex-Uber EM; deep-dives paid/truncated | yes |
| Don't Worry About the Vase | Zvi Mowshowitz | **54** | Widely read AI roundups but no institutional seat; **below feed floor → discover-only** | no |

**Economics / policy (5)**

| Source | Author | Score | Rationale | Paywalled |
|---|---|---|---|---|
| Marginal Revolution | Cowen & Tabarrok | 90 | GMU economics professors; most-cited econ blog ever; originality docked for link-blogging. Cap 10/day | no |
| Noahpinion | Noah Smith | 83 | Econ PhD (Michigan), ex-Bloomberg Opinion | yes |
| Slow Boring | Matthew Yglesias | 72 | Vox co-founder; heavily cited in US policy debate; US-centric | yes |
| The Overshoot | Matthew C. Klein | 68 | Ex-FT Alphaville; co-author "Trade Wars Are Class Wars"; ~monthly cadence | yes |
| Apricitas Economics | Joseph Politano | **57** | Original data work, charts reshared by mainstream econ press; thin affiliation — lower-confidence | no |

**Medicine / health (3)**

| Source | Author | Score | Rationale | Paywalled |
|---|---|---|---|---|
| Ground Truths | Eric Topol | 95 | Scripps founder-director; among most-cited living medical researchers. Exactly the "doctor tracking research" use case | no |
| Your Local Epidemiologist | Katelyn Jetelina | 84 | PhD MPH; used by CDC/White House comms during COVID | no |
| Sensible Medicine | Cifu, Prasad, Mandrola et al. | 75 | Academic physicians (UChicago/UCSF); **deliberately contrarian on some consensus positions — pair with Ground Truths for balance**; group score | yes |

**Science / energy / engineering / law (4)**

| Source | Author | Score | Rationale | Paywalled |
|---|---|---|---|---|
| SCOTUSblog | practitioner group | 90 | Definitive independent SCOTUS coverage, cited by the profession (reclassified from research tier — it's expert analysis, not papers) | no |
| Sustainability by Numbers | Hannah Ritchie | 87 | Our World in Data deputy editor, Edinburgh PhD; feed retitled "By the Numbers" live — keep curated display name | no |
| Construction Physics | Brian Potter | 73 | Structural engineer, IFP senior fellow; cited by NYT/WaPo on construction productivity | no |
| Astral Codex Ten | Scott Alexander | 72 | Practicing psychiatrist; outsized intellectual influence; very long essays — summarizer token-budget note | yes |

**India (4)** — honest caveat: India's individual-expert Substack culture is thinner than US/UK; these skew policy/econ/finance.

| Source | Author | Score | Rationale | Paywalled |
|---|---|---|---|---|
| Anticipating the Unintended | Pranay Kotasthane & RSJ | 73 | Takshashila deputy director; books cited in Indian policy press; co-author semi-anonymous (slight deduction) | no |
| Capitalmind | Deepak Shenoy + team | 67 | Founder of a SEBI-registered PMS; borderline "individual" (firm blog) | no |
| Technopolitik | Takshashila researchers | **64** | Institutional multi-author — score rides on the institution; lower-confidence | no |
| Mostly Economics | Amol Agrawal | **56** | 18+ years running, econ PhD; heavy summarize-and-comment format; lower-confidence | no |

**Verified spares (held, not seeded):** Chartbook/Adam Tooze (~90 — strongest, add first if breadth wanted), Silver Bulletin/Nate Silver (~81), Lenny's Newsletter (~73), ChinaTalk (~66), Volts (~64), The Diff (~61), India Uncut (~60), Kyla's Newsletter (~57), Strange Loop Canon (~56). All curl-verified this run.

### 3.3 Admission & review policy

- **Admission is never automated.** New `expert` sources enter only via a sources.json PR or the auth-gated `POST /admin/sources`, which will require `credibility_score` + `credibility_meta.rationale` for expert types (400 otherwise). No crawler, no auto-discovery.
- **LLM-assisted review (Phase 3) proposes, never decides:** a monthly job re-verifies affiliation/followers for rows unreviewed >90 days and writes `credibility_meta.proposed_score` with `reviewed_by: "llm-proposed"`. A human applies it via `PUT /admin/sources/{id}/credibility`, which sets `reviewed_by: "admin"` — and that flag **locks the row against the 10-minute seed-upsert cycle** (otherwise sources.json would silently clobber manual corrections every 10 minutes).
- **Liability posture:** the score is presented as an *editorial* assessment with rationale on file, never an objective ranking of a named person.
- **Substack licensing reality:** free posts arrive full-text in RSS; paid posts arrive truncated. Truncated items produce thin embeddings — flag descriptions ending in "…" and down-weight in clustering or badge "preview only".

---

## 4. Tier 3 — News Channels (35 verified)

### 4.1 International broadcast / wire (10)

| Source | Feed | Cred | Note |
|---|---|---|---|
| Reuters (via Google News) | `news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en` | 95 | **Gap-fill — current 39 has no Reuters.** Direct feeds retired 2020; legacy feedburner DNS-dead (verified) |
| DW News | `rss.dw.com/rdf/rss-en-all` | 90 | 123KB RDF |
| NHK World (via GN proxy) | `news.google.com/rss/search?q=site:www3.nhk.or.jp&...` | 90 | Direct English feed 404 (discontinued) |
| ABC News Australia | `abc.net.au/news/feed/45910/rss.xml` | 90 | |
| CBC News | `cbc.ca/webfeed/rss/rss-topstories` | 90 | |
| France 24 | `france24.com/en/rss` | 85 | |
| CNA | `channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml` | 85 | SEA focus |
| Sky News | `feeds.skynews.com/feeds/rss/home.xml` | 80 | Only ~10 items — small but fresh |
| Euronews | `euronews.com/rss` | 80 | |
| Al Arabiya (via GN proxy) | `news.google.com/rss/search?q=site:english.alarabiya.net&...` | 70 | Direct feeds 403 bot-block. Saudi-aligned — pairs with existing Al Jazeera for balance |

### 4.2 Global business / finance (7)

| Source | Feed | Cred | Note |
|---|---|---|---|
| Financial Times | `ft.com/rss/home` | 95 | Headline+link only; hard paywall — clusters ride on titles (same as existing WSJ) |
| Bloomberg Markets | `feeds.bloomberg.com/markets/news.rss` | 95 | **NOT discontinued — verified live with today's items**, contrary to suspicion. Paywalled |
| CNBC Top News | `search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114` | 80 | |
| MarketWatch | `feeds.content.dowjones.io/public/rss/mw_topstories` | 80 | |
| Fortune | `fortune.com/feed/` | 80 | Full-content feed; metered paywall |
| Forbes Business | `forbes.com/business/feed/` | 65 | Contributor network dilutes staff work; legacy `/real-time/feed2/` is dead |
| Investing.com | `investing.com/rss/news.rss` | 60 | Syndicator. **Bug bait: non-RFC822 pubDate — feedparser yields no date; fetcher needs fetch-time fallback** |

### 4.3 Asia / geopolitics (4)

| Source | Feed | Cred | Note |
|---|---|---|---|
| Nikkei Asia | `asia.nikkei.com/rss/feed/nar` | 90 | Paywalled |
| SCMP | `scmp.com/rss/91/feed` | 80 | Alibaba-owned — softer on Beijing; paywalled |
| The Straits Times Asia | `straitstimes.com/news/asia/rss.xml` | 80 | Paywalled |
| The Diplomat | `thediplomat.com/feed/` | 80 | Indo-Pacific policy analysis |

### 4.4 India regional / vertical (7)

| Source | Feed | Cred | Note |
|---|---|---|---|
| Frontline | `frontline.thehindu.com/feeder/default.rss` | 85 | Fortnightly — don't alarm on quiet periods |
| Bar & Bench | `barandbench.com/feed` | 85 | India's legal-news leader → **new category `legal`** |
| Deccan Herald | `deccanherald.com/stories.rss` | 80 | Quintype site-wide feed; legacy `/rss/national.rss` is dead |
| The New Indian Express | `newindianexpress.com/stories.rss` | 80 | Same Quintype pattern |
| The Wire | `cms.thewire.in/feed` | 75 | **Must use the cms. host** — `thewire.in/feed` serves HTML |
| Business Today | `businesstoday.in/rssfeeds/?id=home` | 75 | |
| Telangana Today | `telanganatoday.com/feed` | 60 | BRS-party-linked ownership — fine for Hyderabad civic news, discount state politics. ~2MB feed |

### 4.5 Verticals (6)

| Source | Feed | Cred | Note |
|---|---|---|---|
| ESPNcricinfo | `espncricinfo.com/rss/content/story/feeds/0.xml` | 90 | **New category `sports`** |
| Variety | `variety.com/feed/` | 85 | **New category `entertainment`** |
| The Hollywood Reporter | `hollywoodreporter.com/feed/` | 85 | Overlaps Variety — ship both or pick one |
| Rest of World | `restofworld.org/feed/latest/` | 85 | Tech in emerging markets — real gap vs TechCrunch/Verge |
| The Register | `theregister.com/headlines.atom` | 75 | Atom, not RSS — feedparser handles it |
| TechRadar | `techradar.com/rss` | 70 | 846KB full-content feed — heaviest fetch of the batch; review/deals-heavy |

Google-News-proxy entries (Reuters, NHK, Al Arabiya) return `news.google.com` redirect links — the pipeline already tolerates this (existing Business Standard seed uses the same pattern); title-similarity dedup prevents double-counting.

---

## 5. Architecture

Grounded in code read this session: `models.py` (Source/SourceType/User), `fetcher.py` (`ensure_sources`/`fetch_single_feed`), `routes.py` (`get_feed` UER blend, `get_briefing`, `create_source`), migrations head `a2b3c4d5e6f7`.

### 5.1 Schema — and the enum trap

`Source.source_type` is a **native Postgres enum** (`sourcetype`). Three consequences, all verified in the baseline migration:

1. `ALTER TYPE sourcetype ADD VALUE` **cannot run inside the migration transaction** → use Alembic's `autocommit_block()` with `ADD VALUE IF NOT EXISTS` (idempotent vs hand-ALTERed DBs).
2. **Alembic autogenerate will not detect enum additions** — the migration must be hand-written.
3. Environment drift: the dev DB is create_all-managed (no `alembic_version`) → **hand-ALTER the dev enum**; prod runs Alembic on deploy (since commit 5374087) → **verify prod is stamped at head before this ships**, or the deploy migration fails. Downgrade cannot remove enum values (documented irreversible).

New members: `research`, `expert`. New nullable `sources` columns (pure-additive, zero backfill risk):

```
author_name VARCHAR(255) · credibility_score SMALLINT (0-100, NULL = news/unreviewed)
credibility_meta JSONB {affiliation, credentials, rationale, reviewed_by: seed|llm-proposed|admin, proposed_score, last_reviewed}
audience JSONB (["medicine","ai"...]; NULL = everyone) · is_preprint BOOL default false · per_fetch_cap SMALLINT
```

`category` appears to be a plain string (routes' `SOURCE_CATEGORY_DISPLAY` falls back safely on unknowns) — new values `research`, `sports`, `entertainment`, `legal` just need display entries. **Confirm it's not a second native enum before merging.**

`_upsert_sources` extends its existing-row branch to backfill the new fields — **except when `credibility_meta.reviewed_by == "admin"`** (the clobber-lock, §3.3). `SourceOut` gains `author_name`, `credibility_score`, `is_preprint` (additive JSON, backward compatible).

### 5.2 Credibility lifecycle (three effects, bounded)

- **(a) Badge** — `EXPERT · Ben Thompson · 82`, `RESEARCH`, `PREPRINT · not peer-reviewed` chips on StoryCard/SourceCard/DeepDive, same JetBrains-Mono visual family as `src:N · coh:0.XX`. Copy must pass `npm run lint:copy`.
- **(b) Feed-rank multiplier** — inside `get_feed`'s blend: `× (0.9 + 0.2 × score/100)`, i.e. bounded ×[0.9, 1.1]. NULL (news) defaults to neutral 75. Credibility nudges ordering; it can never drown breaking news.
- **(c) Floors** *(gated tiers only — news is curated editorially, no floor)*: `credibility_briefing_floor = 70` (below → never in briefing); feed floor 55 (below → discover/search only; catches Zvi at 54). Search is never gated — explicit query = explicit intent.

### 5.3 Per-persona gating — a hard SQL filter, not a soft weight

Rejected alternatives: briefing-weight-penalty (arXiv singletons would occupy the 20-cluster candidate window before weighting runs), UER (no-op at cold start by design), a new `users.audience_tags` column (unnecessary — derive per-request).

**Mechanism:** `audience.py` maps `User.profession` (free-text keyword map: doctor/physician/MBBS→medicine, lawyer/advocate→law, engineer/developer→software, trader/CFA→finance…) ∪ interest-topic tags → `user_tags`. One WHERE fragment shared by feed and briefing:

```
non-gated source  OR  audience IS NULL  OR  audience ?| user_tags  OR  source followed by user
```

- **Feed:** applied at pool selection (both UER and legacy branches). Empty `user_tags` ⇒ gated+tagged sources never enter — a profession-less user's feed is **byte-identical** to today (same discipline as UER).
- **Briefing:** clusters mix sources, so gate via EXISTS at the article level inside the candidate query; matched research/expert clusters get a small `story_weights` bonus (+0.15) so "for your field" reliably makes the top-8. Verify the join with EXPLAIN (small window, but check).
- **Follow override:** `follows.kind` is free-form String(16) — add convention value `"source"`. Zero migration; following bypasses the gate.
- **Discover deck:** up to ~5 of 25 cards may be gated-tier regardless of match, with a "Follow source" affordance — the opt-in surface; swipes feed UER.

### 5.4 Pipeline fit

- **Do NOT skip embedding/clustering for research** — embeddings power search, topics, UER. Papers become singleton clusters (cosine 0.15 won't merge abstracts with news) and the codebase already tolerates `source_count=1`. Known gap: `graph_extract_min_sources=2` means singleton research clusters skip entity extraction — acceptable now; relax to 1 for research in Phase 3.
- **`per_fetch_cap` enforced in `fetch_single_feed`** (`feed.entries[:cap]`, newest-first): 25 research, 10 high-volume experts, NULL news.
- **Real bug found while reading `fetch_single_feed` (fetcher.py ~L267):** it prefers `entry.summary` over `entry.content` — Substack ships both a short description AND full `content:encoded`, so full text is discarded exactly when available. Fix: take the longer. One line; benefits existing blog sources too.
- **Investing.com pubDate fallback** (non-RFC822 date → fetch-time ordering fallback) — small fetcher patch.
- GDELT untouched; research/expert are RSS-only. Dedup safe (long unique titles).

### 5.5 UI surfacing — minimal-first

Phase-1 mandatory UI = badges only, on existing cards. No new screens. Briefing gets no new rail (bonus-ranked into the existing 8 for matched users; zero change for others). Phase-2: feed filter chips "All · News · Research · Experts" (`GET /feed?source_type=`) + discover-deck follow affordance. A dedicated "For your field" rail is Phase-3-if-engagement-justifies.

---

## 6. Phased Rollout (~4.5–5.5 dev-days)

| Phase | Scope | Effort | Exit criteria |
|---|---|---|---|
| **1 — Seed + gate** | Hand-written migration (enum autocommit block + 6 columns); hand-ALTER dev enum; SourceType/model/SourceOut updates; extend sources.json with the 80 verified entries + hand scores; `_upsert_sources` backfill w/ admin-lock; `audience.py` keyword map; feed+briefing SQL gate + floors; `per_fetch_cap` in fetcher; the `entry.content` and Investing.com pubDate fetcher fixes; expert-validation on POST /admin/sources | **1.5–2 d** | `alembic upgrade head` green on empty DB; pytest green; doctor-persona test user sees NEJM in feed/briefing; profession-less user's responses byte-identical; briefing never crowded by research singletons |
| **2 — Badges + ranking + opt-in** | RESEARCH/EXPERT/PREPRINT badges (Badge.tsx variants, lint:copy); credibility feed multiplier ×[0.9,1.1]; briefing story_weights bonus; discover-deck gated sampling + follow-source (`follows.kind="source"`); `?source_type=` filter chips | **1.5 d** | Preprint badge on every arXiv/medRxiv card; swipe→feedback→UER bump verified; follow bypasses gate |
| **3 — Credibility ops + personal research feeds** | Monthly LLM review job (propose-only) + `PUT /admin/sources/{id}/credibility` (apply + lock); PubMed E-utilities per-specialty adapter (profession→term→esearch/efetch, NCBI api_key, ≤3 req/s); arXiv per-category generator from interests; LLM profession→tags classifier cached on persona_version; consider `graph_extract_min_sources=1` for research | **1.5–2 d** | Review job writes proposals only; a cardiologist gets a weekly PubMed-derived cardiology digest |

**Top risks:** enum-migration/environment drift (mitigate: `IF NOT EXISTS` + verify prod stamp first); volume/cost blowout from arXiv/bioRxiv (mitigate: caps are in Phase 1, not later); brittle free-text profession matching ("cardiologist" ≠ "doctor" — mitigate: generous keyword map now, LLM classifier + follow-override as escape hatches); numeric scores on named individuals (mitigate: editorial framing, rationale on file, human-only admission); feed rot (~30–50% candidate attrition observed this run — re-verify quarterly).

---

## 7. Ready-to-Seed JSON (Phase 1 — VERIFIED feeds only)

⚠️ Entries with `source_type` `research`/`expert` **require the enum migration first** (and the dev-DB hand-ALTER). Categories `research`, `legal`, `sports`, `entertainment` are new string values (add `SOURCE_CATEGORY_DISPLAY` entries). All other fields are additive/nullable. Zvi is seeded with score 54 → automatically discover-only under the 55 feed floor.

```json
[
  {"name": "arXiv cs.AI", "url": "https://arxiv.org/list/cs.AI/recent", "rss_url": "https://rss.arxiv.org/rss/cs.AI", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 80, "audience": ["ai", "software", "research"], "is_preprint": true, "per_fetch_cap": 25},
  {"name": "arXiv cs.LG", "url": "https://arxiv.org/list/cs.LG/recent", "rss_url": "https://rss.arxiv.org/rss/cs.LG", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 80, "audience": ["ai", "software", "research"], "is_preprint": true, "per_fetch_cap": 25},
  {"name": "arXiv econ.GN", "url": "https://arxiv.org/list/econ.GN/recent", "rss_url": "https://rss.arxiv.org/rss/econ.GN", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 75, "audience": ["economics", "finance", "policy"], "is_preprint": true, "per_fetch_cap": 25},
  {"name": "arXiv q-fin", "url": "https://arxiv.org/list/q-fin/recent", "rss_url": "https://rss.arxiv.org/rss/q-fin", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 75, "audience": ["finance", "trading", "research"], "is_preprint": true, "per_fetch_cap": 25},
  {"name": "medRxiv", "url": "https://www.medrxiv.org", "rss_url": "https://connect.medrxiv.org/medrxiv_xml.php?subject=all", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 70, "audience": ["medicine", "publichealth"], "is_preprint": true, "per_fetch_cap": 25},
  {"name": "bioRxiv", "url": "https://www.biorxiv.org", "rss_url": "https://connect.biorxiv.org/biorxiv_xml.php?subject=all", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 72, "audience": ["biology", "biotech", "medicine"], "is_preprint": true, "per_fetch_cap": 25},
  {"name": "New England Journal of Medicine", "url": "https://www.nejm.org", "rss_url": "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss", "is_paywalled": true, "source_type": "research", "region": "global", "category": "research", "credibility_score": 98, "audience": ["medicine"], "per_fetch_cap": 25},
  {"name": "The Lancet", "url": "https://www.thelancet.com", "rss_url": "https://www.thelancet.com/rssfeed/lancet_current.xml", "is_paywalled": true, "source_type": "research", "region": "global", "category": "research", "credibility_score": 98, "audience": ["medicine", "publichealth"], "per_fetch_cap": 25},
  {"name": "JAMA", "url": "https://jamanetwork.com/journals/jama", "rss_url": "https://jamanetwork.com/rss/site_3/67.xml", "is_paywalled": true, "source_type": "research", "region": "global", "category": "research", "credibility_score": 97, "audience": ["medicine"], "per_fetch_cap": 25},
  {"name": "Nature Medicine", "url": "https://www.nature.com/nm/", "rss_url": "https://www.nature.com/nm.rss", "is_paywalled": true, "source_type": "research", "region": "global", "category": "research", "credibility_score": 95, "audience": ["medicine", "biotech"], "per_fetch_cap": 25},
  {"name": "Nature", "url": "https://www.nature.com", "rss_url": "https://www.nature.com/nature.rss", "is_paywalled": true, "source_type": "research", "region": "global", "category": "research", "credibility_score": 98, "audience": ["science", "research"], "per_fetch_cap": 25},
  {"name": "Science News (AAAS)", "url": "https://www.science.org/news", "rss_url": "https://www.science.org/rss/news_current.xml", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 90, "per_fetch_cap": 25},
  {"name": "Science Current Issue", "url": "https://www.science.org", "rss_url": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science", "is_paywalled": true, "source_type": "research", "region": "global", "category": "research", "credibility_score": 98, "audience": ["science", "research"], "per_fetch_cap": 25},
  {"name": "PLOS ONE", "url": "https://journals.plos.org/plosone/", "rss_url": "https://journals.plos.org/plosone/feed/atom", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 85, "audience": ["science", "medicine", "research"], "per_fetch_cap": 25},
  {"name": "PNAS", "url": "https://www.pnas.org", "rss_url": "https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 93, "audience": ["science", "research"], "per_fetch_cap": 25},
  {"name": "ScienceDaily", "url": "https://www.sciencedaily.com", "rss_url": "https://www.sciencedaily.com/rss/all.xml", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 60, "per_fetch_cap": 25},
  {"name": "Quanta Magazine", "url": "https://www.quantamagazine.org", "rss_url": "https://www.quantamagazine.org/feed/", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 88, "per_fetch_cap": 25},
  {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org", "rss_url": "https://spectrum.ieee.org/feeds/feed.rss", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 85, "audience": ["engineering", "technology"], "per_fetch_cap": 25},
  {"name": "ACM TechNews", "url": "https://technews.acm.org", "rss_url": "https://technews.acm.org/rss/technews.xml", "is_paywalled": false, "source_type": "research", "region": "global", "category": "research", "credibility_score": 82, "audience": ["software", "research"], "per_fetch_cap": 25},

  {"name": "Stratechery", "url": "https://stratechery.com", "rss_url": "https://stratechery.com/feed/", "is_paywalled": true, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Ben Thompson", "credibility_score": 82, "audience": ["technology", "business"], "credibility_meta": {"rationale": "Aggregation Theory canon; Kellogg MBA; industry-standard read", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "One Useful Thing", "url": "https://www.oneusefulthing.org", "rss_url": "https://www.oneusefulthing.org/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Ethan Mollick", "credibility_score": 92, "credibility_meta": {"rationale": "Wharton professor, MIT PhD; most-cited academic voice on AI at work", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "AI as Normal Technology", "url": "https://www.aisnakeoil.com", "rss_url": "https://www.aisnakeoil.com/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Arvind Narayanan & Sayash Kapoor", "credibility_score": 88, "audience": ["ai", "policy", "technology"], "credibility_meta": {"rationale": "Princeton CS professor + researcher; AI Snake Oil book; TIME100 AI", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Interconnects", "url": "https://www.interconnects.ai", "rss_url": "https://www.interconnects.ai/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Nathan Lambert", "credibility_score": 79, "audience": ["ai", "software"], "credibility_meta": {"rationale": "AI2 research scientist; Berkeley PhD; ex-HuggingFace RLHF lead", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Import AI", "url": "https://importai.substack.com", "rss_url": "https://importai.substack.com/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Jack Clark", "credibility_score": 78, "audience": ["ai", "policy"], "credibility_meta": {"rationale": "Anthropic co-founder; ex-OpenAI policy director; congressional testimony", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Benedict Evans", "url": "https://www.ben-evans.com", "rss_url": "https://www.ben-evans.com/benedictevans?format=rss", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Benedict Evans", "credibility_score": 76, "audience": ["technology", "business"], "credibility_meta": {"rationale": "Ex-a16z partner; annual trends deck is an industry staple", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "SemiAnalysis", "url": "https://semianalysis.com", "rss_url": "https://semianalysis.com/feed/", "is_paywalled": true, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Dylan Patel", "credibility_score": 76, "audience": ["technology", "finance"], "credibility_meta": {"rationale": "Semiconductor research firm cited by WSJ/Bloomberg; no formal credential (flagged)", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Simon Willison's Weblog", "url": "https://simonwillison.net", "rss_url": "https://simonwillison.net/atom/everything/", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Simon Willison", "credibility_score": 73, "audience": ["software", "ai"], "per_fetch_cap": 10, "credibility_meta": {"rationale": "Django co-creator; de-facto practical LLM-engineering reference", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "The Pragmatic Engineer", "url": "https://newsletter.pragmaticengineer.com", "rss_url": "https://newsletter.pragmaticengineer.com/feed", "is_paywalled": true, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Gergely Orosz", "credibility_score": 72, "audience": ["software"], "credibility_meta": {"rationale": "#1 tech Substack (>900k subs); ex-Uber engineering manager", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Don't Worry About the Vase", "url": "https://thezvi.substack.com", "rss_url": "https://thezvi.substack.com/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "technology", "author_name": "Zvi Mowshowitz", "credibility_score": 54, "audience": ["ai"], "per_fetch_cap": 10, "credibility_meta": {"rationale": "Widely read AI roundups; no institutional seat; LOWER-CONFIDENCE score; below feed floor - discover-only", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Marginal Revolution", "url": "https://marginalrevolution.com", "rss_url": "https://marginalrevolution.com/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "business", "author_name": "Tyler Cowen & Alex Tabarrok", "credibility_score": 90, "per_fetch_cap": 10, "credibility_meta": {"rationale": "GMU econ professors; most-cited econ blog; heavy link-blogging docked", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Noahpinion", "url": "https://www.noahpinion.blog", "rss_url": "https://www.noahpinion.blog/feed", "is_paywalled": true, "source_type": "expert", "region": "global", "category": "business", "author_name": "Noah Smith", "credibility_score": 83, "audience": ["economics", "finance"], "credibility_meta": {"rationale": "Econ PhD (Michigan); ex-Bloomberg Opinion columnist", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Slow Boring", "url": "https://www.slowboring.com", "rss_url": "https://www.slowboring.com/feed", "is_paywalled": true, "source_type": "expert", "region": "global", "category": "policy", "author_name": "Matthew Yglesias", "credibility_score": 72, "audience": ["policy"], "credibility_meta": {"rationale": "Vox co-founder; heavily cited in US policy debate; US-centric", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "The Overshoot", "url": "https://theovershoot.co", "rss_url": "https://theovershoot.co/feed", "is_paywalled": true, "source_type": "expert", "region": "global", "category": "business", "author_name": "Matthew C. Klein", "credibility_score": 68, "audience": ["economics", "finance"], "credibility_meta": {"rationale": "Ex-FT Alphaville; co-author Trade Wars Are Class Wars; low cadence", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Apricitas Economics", "url": "https://www.apricitas.io", "rss_url": "https://www.apricitas.io/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "business", "author_name": "Joseph Politano", "credibility_score": 57, "audience": ["economics", "finance"], "credibility_meta": {"rationale": "Original data work reshared by mainstream econ press; thin affiliation; LOWER-CONFIDENCE score", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Ground Truths", "url": "https://erictopol.substack.com", "rss_url": "https://erictopol.substack.com/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "science", "author_name": "Eric Topol", "credibility_score": 95, "audience": ["medicine", "science"], "credibility_meta": {"rationale": "Scripps Research founder-director; among most-cited living medical researchers", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Your Local Epidemiologist", "url": "https://yourlocalepidemiologist.substack.com", "rss_url": "https://yourlocalepidemiologist.substack.com/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "science", "author_name": "Katelyn Jetelina", "credibility_score": 84, "audience": ["medicine", "publichealth"], "credibility_meta": {"rationale": "PhD MPH epidemiologist; used by CDC/White House comms", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Sensible Medicine", "url": "https://www.sensible-med.com", "rss_url": "https://www.sensible-med.com/feed", "is_paywalled": true, "source_type": "expert", "region": "global", "category": "science", "author_name": "Cifu, Prasad, Mandrola et al.", "credibility_score": 75, "audience": ["medicine"], "credibility_meta": {"rationale": "Academic physicians; deliberately contrarian on some consensus positions - pair with Ground Truths; group score", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "SCOTUSblog", "url": "https://www.scotusblog.com", "rss_url": "https://www.scotusblog.com/feed/", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "legal", "author_name": "SCOTUSblog contributors", "credibility_score": 90, "audience": ["law"], "credibility_meta": {"rationale": "Definitive independent US Supreme Court coverage, cited by practitioners", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Sustainability by Numbers", "url": "https://www.sustainabilitybynumbers.com", "rss_url": "https://www.sustainabilitybynumbers.com/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "science", "author_name": "Hannah Ritchie", "credibility_score": 87, "audience": ["energy", "science"], "credibility_meta": {"rationale": "Our World in Data deputy editor; Edinburgh PhD; feed retitled By the Numbers - keep curated name", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Construction Physics", "url": "https://www.construction-physics.com", "rss_url": "https://www.construction-physics.com/feed", "is_paywalled": false, "source_type": "expert", "region": "global", "category": "science", "author_name": "Brian Potter", "credibility_score": 73, "audience": ["engineering", "policy"], "credibility_meta": {"rationale": "Structural engineer; IFP senior fellow; cited by NYT/WaPo", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Astral Codex Ten", "url": "https://www.astralcodexten.com", "rss_url": "https://www.astralcodexten.com/feed", "is_paywalled": true, "source_type": "expert", "region": "global", "category": "science", "author_name": "Scott Alexander", "credibility_score": 72, "credibility_meta": {"rationale": "Practicing psychiatrist; outsized intellectual influence; very long essays", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Anticipating the Unintended", "url": "https://publicpolicy.substack.com", "rss_url": "https://publicpolicy.substack.com/feed", "is_paywalled": false, "source_type": "expert", "region": "in", "category": "policy", "author_name": "Pranay Kotasthane & RSJ", "credibility_score": 73, "audience": ["policy"], "credibility_meta": {"rationale": "Takshashila deputy director; books cited in Indian policy press", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Capitalmind", "url": "https://www.capitalmind.in", "rss_url": "https://www.capitalmind.in/feed/", "is_paywalled": false, "source_type": "expert", "region": "in", "category": "business", "author_name": "Deepak Shenoy", "credibility_score": 67, "audience": ["finance"], "credibility_meta": {"rationale": "Founder of SEBI-registered PMS; practitioner track; firm blog (borderline individual)", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Technopolitik", "url": "https://hightechir.substack.com", "rss_url": "https://hightechir.substack.com/feed", "is_paywalled": false, "source_type": "expert", "region": "in", "category": "policy", "author_name": "Takshashila researchers", "credibility_score": 64, "audience": ["policy", "technology"], "credibility_meta": {"rationale": "Institutional multi-author; LOWER-CONFIDENCE score", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},
  {"name": "Mostly Economics", "url": "https://mostlyeconomics.wordpress.com", "rss_url": "https://mostlyeconomics.wordpress.com/feed/", "is_paywalled": false, "source_type": "expert", "region": "in", "category": "business", "author_name": "Amol Agrawal", "credibility_score": 56, "audience": ["economics", "finance"], "credibility_meta": {"rationale": "Econ PhD, 18+ yrs running; summarize-and-comment heavy; LOWER-CONFIDENCE score", "reviewed_by": "seed", "last_reviewed": "2026-07-03"}},

  {"name": "Reuters", "url": "https://www.reuters.com", "rss_url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en", "is_paywalled": false, "source_type": "wire", "region": "global", "category": "world"},
  {"name": "DW News", "url": "https://www.dw.com/en", "rss_url": "https://rss.dw.com/rdf/rss-en-all", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "France 24", "url": "https://www.france24.com/en/", "rss_url": "https://www.france24.com/en/rss", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "CNA", "url": "https://www.channelnewsasia.com", "rss_url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "NHK World Japan", "url": "https://www3.nhk.or.jp/nhkworld/", "rss_url": "https://news.google.com/rss/search?q=site:www3.nhk.or.jp&hl=en-US&gl=US&ceid=US:en", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "Al Arabiya English", "url": "https://english.alarabiya.net", "rss_url": "https://news.google.com/rss/search?q=site:english.alarabiya.net&hl=en-US&gl=US&ceid=US:en", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "ABC News Australia", "url": "https://www.abc.net.au/news", "rss_url": "https://www.abc.net.au/news/feed/45910/rss.xml", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "CBC News", "url": "https://www.cbc.ca/news", "rss_url": "https://www.cbc.ca/webfeed/rss/rss-topstories", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "Sky News", "url": "https://news.sky.com", "rss_url": "https://feeds.skynews.com/feeds/rss/home.xml", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "Euronews", "url": "https://www.euronews.com", "rss_url": "https://www.euronews.com/rss", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "world"},
  {"name": "CNBC", "url": "https://www.cnbc.com", "rss_url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "business"},
  {"name": "Financial Times", "url": "https://www.ft.com", "rss_url": "https://www.ft.com/rss/home", "is_paywalled": true, "source_type": "newspaper", "region": "global", "category": "business"},
  {"name": "Bloomberg Markets", "url": "https://www.bloomberg.com/markets", "rss_url": "https://feeds.bloomberg.com/markets/news.rss", "is_paywalled": true, "source_type": "wire", "region": "global", "category": "business"},
  {"name": "MarketWatch", "url": "https://www.marketwatch.com", "rss_url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "is_paywalled": false, "source_type": "newspaper", "region": "global", "category": "business"},
  {"name": "Investing.com", "url": "https://www.investing.com", "rss_url": "https://www.investing.com/rss/news.rss", "is_paywalled": false, "source_type": "other", "region": "global", "category": "business"},
  {"name": "Fortune", "url": "https://fortune.com", "rss_url": "https://fortune.com/feed/", "is_paywalled": true, "source_type": "newspaper", "region": "global", "category": "business"},
  {"name": "Forbes Business", "url": "https://www.forbes.com", "rss_url": "https://www.forbes.com/business/feed/", "is_paywalled": false, "source_type": "newspaper", "region": "global", "category": "business"},
  {"name": "South China Morning Post", "url": "https://www.scmp.com", "rss_url": "https://www.scmp.com/rss/91/feed", "is_paywalled": true, "source_type": "newspaper", "region": "global", "category": "world"},
  {"name": "Nikkei Asia", "url": "https://asia.nikkei.com", "rss_url": "https://asia.nikkei.com/rss/feed/nar", "is_paywalled": true, "source_type": "newspaper", "region": "global", "category": "business"},
  {"name": "The Diplomat", "url": "https://thediplomat.com", "rss_url": "https://thediplomat.com/feed/", "is_paywalled": false, "source_type": "blog", "region": "global", "category": "policy"},
  {"name": "The Straits Times", "url": "https://www.straitstimes.com", "rss_url": "https://www.straitstimes.com/news/asia/rss.xml", "is_paywalled": true, "source_type": "newspaper", "region": "global", "category": "world"},
  {"name": "Deccan Herald", "url": "https://www.deccanherald.com", "rss_url": "https://www.deccanherald.com/stories.rss", "is_paywalled": false, "source_type": "newspaper", "region": "in", "category": "national"},
  {"name": "The Wire", "url": "https://thewire.in", "rss_url": "https://cms.thewire.in/feed", "is_paywalled": false, "source_type": "blog", "region": "in", "category": "national"},
  {"name": "Telangana Today", "url": "https://telanganatoday.com", "rss_url": "https://telanganatoday.com/feed", "is_paywalled": false, "source_type": "newspaper", "region": "in", "category": "national"},
  {"name": "The New Indian Express", "url": "https://www.newindianexpress.com", "rss_url": "https://www.newindianexpress.com/stories.rss", "is_paywalled": false, "source_type": "newspaper", "region": "in", "category": "national"},
  {"name": "Business Today", "url": "https://www.businesstoday.in", "rss_url": "https://www.businesstoday.in/rssfeeds/?id=home", "is_paywalled": false, "source_type": "newspaper", "region": "in", "category": "business"},
  {"name": "Frontline", "url": "https://frontline.thehindu.com", "rss_url": "https://frontline.thehindu.com/feeder/default.rss", "is_paywalled": false, "source_type": "newspaper", "region": "in", "category": "policy"},
  {"name": "Bar & Bench", "url": "https://www.barandbench.com", "rss_url": "https://www.barandbench.com/feed", "is_paywalled": false, "source_type": "blog", "region": "in", "category": "legal"},
  {"name": "ESPNcricinfo", "url": "https://www.espncricinfo.com", "rss_url": "https://www.espncricinfo.com/rss/content/story/feeds/0.xml", "is_paywalled": false, "source_type": "channel", "region": "global", "category": "sports"},
  {"name": "Variety", "url": "https://variety.com", "rss_url": "https://variety.com/feed/", "is_paywalled": false, "source_type": "newspaper", "region": "global", "category": "entertainment"},
  {"name": "The Hollywood Reporter", "url": "https://www.hollywoodreporter.com", "rss_url": "https://www.hollywoodreporter.com/feed/", "is_paywalled": false, "source_type": "newspaper", "region": "global", "category": "entertainment"},
  {"name": "TechRadar", "url": "https://www.techradar.com", "rss_url": "https://www.techradar.com/rss", "is_paywalled": false, "source_type": "blog", "region": "global", "category": "technology"},
  {"name": "The Register", "url": "https://www.theregister.com", "rss_url": "https://www.theregister.com/headlines.atom", "is_paywalled": false, "source_type": "blog", "region": "global", "category": "technology"},
  {"name": "Rest of World", "url": "https://restofworld.org", "rss_url": "https://restofworld.org/feed/latest/", "is_paywalled": false, "source_type": "blog", "region": "global", "category": "technology"}
]
```

---

## Appendix A — Unverified / dead / deferred (do NOT seed)

| Candidate | Failure | Disposition |
|---|---|---|
| BMJ (`bmj.com/rss/*`) | 403 Cloudflare on all variants | Retry with browser UA or Google-News `site:` proxy (the Business Standard pattern) |
| NBER new working papers | 403 Akamai "Access Denied" | Same retry path; econ persona covered by arXiv econ.GN meanwhile |
| SSRN | 403/404 on RSS endpoints | Same |
| Lawfare | 403/404 on all rss/feed variants | Same; US-law persona has SCOTUSblog |
| PRS Legislative Research (India) | 404/500 | Same; India-policy persona has Anticipating the Unintended + Frontline |
| PubMed literal RSS (`/rss/search/<GUID>/`) | GUID minting is CSRF/session-gated (403 scripted; 500 synthetic key) | Superseded by the verified E-utilities pipeline (Phase 3) |
| Supreme Court Observer (India) | Feed live but STALE — 1 item, lastBuildDate Apr 2022 | Re-check for a current feed path before adding |
| CEPR / VoxEU | Feed returns stale taxonomy pages, not articles; `voxeu.org/feed` 404 | Revisit for a working article feed |
| feeds.reuters.com | DNS dead (exit 000) | Replaced by Google News proxy (seeded) |
| NHK direct English feed | 404 (discontinued) | Replaced by GN proxy (seeded) |
| Al Arabiya direct feeds | 403 bot-block | Replaced by GN proxy (seeded) |
| Forbes `/real-time/feed2/` | 404 | Replaced by `/business/feed/` (seeded) |
| Deccan Herald `/rss/national.rss`, `/rss/top.rss` | 404 | Replaced by Quintype `/stories.rss` (seeded) |
| `thewire.in/feed` | 200 but serves HTML | Replaced by `cms.thewire.in/feed` (seeded) |
| TNIE legacy `?getXmlFeed=true` | 404 | Replaced by `/stories.rss` (seeded) |
| Matt Levine — Money Stuff | No public RSS (Bloomberg email only) | Excluded |
| Doomberg | Anonymous author — rubric unscorable | Excluded by policy |
| "Paper Planes" (from brief) | Could not be confidently identified as a live expert feed | Not proposed rather than guessed |

**Appendix B — verification detail retention:** full per-feed verifyNotes (item counts, feed sizes, encoding quirks, alternate feed URLs) are preserved in the three research payloads; carry them into the PR description when seeding so future re-verification has a baseline.
