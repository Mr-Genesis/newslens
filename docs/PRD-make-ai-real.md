# Make the AI Real — PRD

> Created using PM Skills: `prd-development` template

## 1. Executive Summary

NewsLens promises "AI-powered news intelligence" but currently delivers raw article snippets as summaries, hardcoded confidence scores, and keyword-based topic matching. This PRD covers the work to make the AI pipeline functional: real GPT-4o-mini summaries, embedding-based topic assignment, adaptive explore/exploit recommendations, read state tracking, and public deployment — transforming the demo into a product that delivers its core value proposition.

## 2. Problem Statement

**Who:** Any NewsLens user opening the briefing or discover screens.

**What:** The AI features are entirely stubbed:
- Every cluster shows `coherence: 0.85` regardless of actual quality
- "AI summaries" are just the first article's snippet truncated to 2 sentences
- Topic assignment uses naive substring matching (`"science" in text`) — an article about "science fiction" gets tagged "Science"
- The feed never adapts to user preferences (explore ratio hardcoded at 0.3)
- Stories never show as "read" even after opening them

**Why it's painful:** The product makes promises it can't keep. Users lose trust when they notice every story has the same confidence score, and engagement stalls when swiping has no effect on their feed.

**Evidence:**
- 100% of briefing stories show `coherence: 0.85` (hardcoded at `routes.py:295`)
- `assign_topics()` in `fetcher.py:18` uses `if keyword in text_to_match` — a known misclassification source
- `explore_ratio=0.3` is returned as a constant (`routes.py:140`)
- `is_read=False` is always returned (`routes.py:296`)
- No public URL exists — the APK only works via `10.0.2.2:8000` (emulator localhost)

## 3. Target Users & Personas

**Primary: The Informed Professional**
- Reads news daily, wants multi-source perspective
- Values trust signals (source count, confidence scores)
- Expects the app to learn their interests over time
- Uses the app on mobile during commute/breaks

**Secondary: The Curious Explorer**
- Discovers new topics through the swipe deck
- Wants the app to surface surprising, relevant stories
- Judges the product by how quickly it adapts to their interests

**Jobs-to-be-done:**
1. "Help me understand what happened today, from multiple sources" (briefing)
2. "Show me stories I wouldn't have found on my own" (discover)
3. "Remember what I've read and adapt to my interests" (personalization)

## 4. Strategic Context

**Business Goal:** Transform NewsLens from an MVP demo to a product that can be shared with real users and gather meaningful feedback.

**Why Now:**
- The data pipeline is solid (RSS + GDELT fetching, embedding generation, clustering all work)
- The UI is built and mobile-optimized (14 topics seeded, 4 screens, bottom tab bar)
- Only the AI layer is missing — the highest-leverage work possible
- OpenAI API infrastructure is in place (per-user encrypted keys, client patterns)

**Competitive Landscape:** News aggregators (Google News, Apple News, Artifact RIP) all have AI summaries. Without real summaries, NewsLens is just an RSS reader with extra steps.

## 5. Solution Overview

### Feature 1: Real AI Summaries (hybrid batch + on-demand)
- **Batch job** (APScheduler, every 10 min): generates GPT-4o-mini summaries for clusters missing them
- **On-demand fallback**: `/briefing` and `/clusters/{id}` generate summaries if the batch missed them
- **Coherence score**: derived from source count (1 source = 0.65, 2 = 0.75, 3+ = 0.85, 5+ = 0.95)
- **Graceful degradation**: if OpenAI is down, return snippet with `coherence: 0.70`

### Feature 2: Embedding-Based Topic Assignment
- Replace `assign_topics()` keyword matching with cosine similarity
- Seed topic embeddings on startup (14 topics × OpenAI embedding call)
- Assign topics where cosine distance < 0.6 threshold
- New APScheduler job runs after embedding backfill

### Feature 3: Read State Tracking
- New `FeedbackType.read` enum value
- `GET /clusters/{id}` marks articles as read
- `GET /briefing` returns `is_read: true` for previously opened stories

### Feature 4: Explore/Exploit from Preferences
- Query `user_preferences` for topic weights
- Sort briefing stories by preference weight (exploit)
- Reserve 2 of 8 slots for low-weight topics (explore)
- Compute real explore_ratio from recent feedback

### Feature 5: Backend Deployment
- Deploy to Fly.io or Render (Dockerfile ready)
- Managed PostgreSQL with pgvector
- Update Capacitor build with public URL

## 6. Success Metrics

| Metric | Current | Target | Type |
|--------|---------|--------|------|
| Unique coherence scores in briefing | 1 (always 0.85) | 3+ distinct values | Primary |
| Topic assignment accuracy | ~30% (keyword matching) | >70% (embedding similarity) | Primary |
| Stories with AI-generated summaries | 0% | >80% of clustered stories | Primary |
| Read state tracked in briefing | 0% (always false) | 100% of opened stories | Secondary |
| Feed adapts to swipe behavior | No | Yes (explore_ratio varies) | Secondary |
| Public URL reachable | No | Yes | Guardrail |

## 7. User Stories & Requirements

### Epic: Real AI Summaries
**Hypothesis:** We believe that replacing stub summaries with GPT-4o-mini generated summaries will make the briefing trustworthy because users will see contextual, multi-source synthesis instead of raw snippets.

**Stories:**
- As a reader, I want each briefing story to have a real AI summary so I can quickly understand the key facts
- As a reader, I want confidence scores to reflect actual source diversity so I can gauge story reliability
- As a reader, I want summaries to generate within 10 minutes of new clusters forming so my briefing stays fresh

**Acceptance Criteria:**
- [ ] Summaries are 2-3 sentences, generated by GPT-4o-mini
- [ ] Coherence varies by source count (0.65-0.95 range)
- [ ] Batch job processes up to 5 clusters per run
- [ ] If OpenAI is down, fallback to snippet with 0.70 coherence

### Epic: Smart Topic Assignment
**Hypothesis:** We believe embedding-based topic assignment will correctly categorize >70% of articles because cosine similarity captures semantic meaning better than keyword matching.

**Stories:**
- As a reader, I want articles correctly categorized by topic so my briefing sections are relevant
- As a reader, I want new topics to be assigned automatically as articles are embedded

**Acceptance Criteria:**
- [ ] Topic embeddings seeded on startup (14 topics)
- [ ] Articles assigned topics via cosine distance < 0.6
- [ ] Assignment runs as scheduled job every 10 minutes
- [ ] Keyword matching removed as primary assignment method

### Epic: Read State
**Stories:**
- As a reader, I want to see which briefing stories I've already read so I don't re-open them
- [ ] Opening a story detail marks it as read
- [ ] Briefing shows `is_read: true` for previously opened stories
- [ ] Unread indicator (amber dot) only appears on unread stories

### Epic: Adaptive Feed
**Stories:**
- As a reader, I want my briefing to prioritize topics I engage with so it becomes more relevant over time
- [ ] Briefing sorts stories by user topic preference weights
- [ ] 2 of 8 slots reserved for exploration (low-weight topics)
- [ ] Explore ratio computed from recent feedback window

### Epic: Public Deployment
**Stories:**
- As a reader, I want to access NewsLens from any device via a public URL
- [ ] Backend deployed to Fly.io or Render
- [ ] Health endpoint responds at public URL
- [ ] Capacitor APK updated with public backend URL

## 8. Out of Scope

- **User authentication** — Sprint 2 (current single-user MVP is acceptable for initial testing)
- **Search** — Sprint 2 (pgvector infrastructure ready but not needed for core AI validation)
- **Push notifications** — Sprint 3 (requires auth + device registration)
- **SSE real-time updates** — 10-min APScheduler refresh is sufficient for MVP
- **AI tension lines** — Lower priority; current title-as-tension-line works

## 9. Dependencies & Risks

**Technical Dependencies:**
- OpenAI API key (per-user encrypted, or env var fallback)
- PostgreSQL + pgvector (running in Docker)
- Existing embedding pipeline (generates embeddings for new articles every 5 min)

**Risks:**
| Risk | Mitigation |
|------|-----------|
| OpenAI API costs spike | Batch size limited to 5, summaries cached 4+ hours |
| Topic embeddings don't cluster well | Tunable threshold (0.6), keyword fallback preserved |
| Deployment free tier limits | Render/Fly.io both offer generous free tiers |
| Migrations break existing data | `ALTER TABLE IF NOT EXISTS` pattern, Docker recreatable |

## 10. Open Questions

- Should coherence be purely source-count based, or also factor in embedding cluster tightness?
- What's the right staleness threshold for re-generating summaries? (currently 4 hours)
- Should the batch job run on a staggered schedule vs. fixed interval to avoid API rate limits?
