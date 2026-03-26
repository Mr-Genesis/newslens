# NewsLens Product Roadmap

> Generated using PM Skills: `roadmap-planning` + `prioritization-advisor` (RICE framework)

## Strategy Context

**Business Goal:** Transform NewsLens from an RSS-reader demo into a real AI-powered news intelligence product that delivers its core promise — multi-source story clustering with AI summaries.

**Customer Problems:**
1. AI summaries are fake (hardcoded coherence, snippet as summary) — destroys trust
2. Topic assignment is broken (naive keyword matching misclassifies articles)
3. Feed doesn't learn from user behavior (explore/exploit ratio hardcoded)
4. App only works on developer's machine (no public deployment)
5. No way to find a story you saw yesterday (no search)

**Constraints:**
- Solo developer on Windows ARM (Turbopack broken, backend in Docker)
- Single-user MVP (no auth yet)
- OpenAI API cost sensitivity (per-user keys, batched calls)

---

## Initiatives (Epics with RICE Scoring)

| # | Epic | Hypothesis | Metric | Reach | Impact | Conf. | Effort | RICE |
|---|------|-----------|--------|-------|--------|-------|--------|------|
| E1 | Real AI Summaries | GPT-4o-mini summaries will make briefings trustworthy | Summary quality rating | 100% users | 3 (massive) | 90% | 1w (S) | **270** |
| E2 | Embedding Topic Assignment | Cosine similarity will fix miscategorized articles | Topic accuracy % | 100% | 2 (high) | 85% | 0.5w (S) | **340** |
| E3 | Read State Tracking | Tracking read stories makes briefing feel responsive | Repeat visit rate | 100% | 2 (high) | 95% | 0.25w (XS) | **760** |
| E4 | Explore/Exploit | Preference-driven feed will increase engagement | Swipe right ratio | 80% | 2 (high) | 70% | 0.5w (S) | **224** |
| E5 | Backend Deployment | Public URL enables APK on real devices | Devices reached | 100% | 3 (massive) | 95% | 0.5w (S) | **570** |
| E6 | User Authentication | Multi-user support prevents data corruption | User count | 50% | 2 (high) | 80% | 1w (S) | **80** |
| E7 | Search | Finding past stories is essential for returning users | Retention D7 | 80% | 2 (high) | 75% | 0.5w (S) | **240** |
| E8 | Error/Offline Handling | Graceful failures prevent user frustration | Error-induced churn | 60% | 1 (medium) | 90% | 0.5w (S) | **108** |
| E9 | Content Freshness | Stale detection prevents showing old news as new | Briefing trust score | 100% | 1 (medium) | 85% | 0.25w (XS) | **340** |
| E10 | Pull-to-Refresh | Native gesture improves mobile UX | Session frequency | 70% | 1 (medium) | 90% | 0.25w (XS) | **252** |
| E11 | AI Tension Lines | GPT hooks make discover deck more compelling | Swipe engagement | 60% | 1 (medium) | 60% | 0.5w (S) | **72** |
| E12 | Onboarding Flow | Topic picker + swipe tutorial reduces first-session confusion | Activation rate | 100% | 2 (high) | 70% | 0.5w (S) | **280** |

---

## Roadmap (Now / Next / Later)

| Stage | Initiative | Outcome | Metric | Notes |
|---|---|---|---|---|
| **Now** | E1: Real AI Summaries | Trustworthy briefings | Summary quality | GPT-4o-mini, hybrid batch+on-demand |
| **Now** | E2: Embedding Topics | Accurate categorization | Topic accuracy | Replace keyword matching with cosine similarity |
| **Now** | E3: Read State | Responsive briefing | Unread accuracy | Trivial effort, high impact |
| **Now** | E4: Explore/Exploit | Adaptive feed | Engagement lift | Uses existing preference weights |
| **Now** | E5: Deploy Backend | Real device access | Devices reached | Fly.io/Render, Dockerfile ready |
| **Next** | E6: User Auth | Multi-user support | User count | JWT or session-based |
| **Next** | E7: Search | Find past stories | Retention D7 | pgvector semantic search |
| **Next** | E12: Onboarding | First-time user activation | Activation rate | Topic picker + swipe tutorial |
| **Next** | E8: Error/Offline | Graceful failures | Error churn reduction | Retry logic + offline banner |
| **Next** | E9: Content Freshness | No stale news | Trust score | Time-window queries + "last updated" UI |
| **Later** | E10: Pull-to-Refresh | Mobile polish | Session frequency | Design-system specced |
| **Later** | E11: AI Tension Lines | Discover engagement | Swipe rate | Depends on E1 (summaries working) |
| **Later** | Push Notifications | Breaking news alerts | Retention D30 | Capacitor push plugin |
| **Later** | Analytics Dashboard | Usage insights | Data-driven decisions | Token cost tracking |
| **Later** | Data Retention Policy | Performance at scale | Query latency p99 | Archive articles >30 days |

---

## Sequencing

### Sprint 1 — NOW (This week): Make the AI Real + Deploy
```
E3: Read State (0.25w)          ─── no dependencies
E2: Topic Embeddings (0.5w)     ─── depends on embedding pipeline
E1: AI Summaries (1w)           ─── depends on OpenAI client pattern
E4: Explore/Exploit (0.5w)      ─── depends on E2 (topic assignment)
E5: Deploy Backend (0.5w)       ─── no dependencies, can parallel
```

### Sprint 2 — NEXT (Weeks 2-3): Multi-User + Discovery
```
E6: User Auth (1w)              ─── unblocks multi-user
E7: Search (0.5w)               ─── depends on pgvector (ready)
E12: Onboarding (0.5w)          ─── depends on E6 (auth)
E8: Error/Offline (0.5w)        ─── no dependencies
E9: Content Freshness (0.25w)   ─── no dependencies
```

### Sprint 3 — LATER (Week 4+): Polish + Retention
```
E10: Pull-to-Refresh
E11: AI Tension Lines           ─── depends on E1
Push Notifications
Analytics
Data Retention
```

---

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| OpenAI API costs spike with real summaries | Medium | High | Batch job with `summary_batch_size=5`, cache summaries for 4h |
| Topic embeddings don't cluster well | Low | Medium | Tunable threshold (0.6), fallback to keyword matching |
| Fly.io free tier hits limits | Low | Medium | Render as backup, or upgrade to paid tier |
| Windows ARM breaks migration tooling | Medium | Low | Run migrations inside Docker container |
| Single-user data gets corrupted before auth | High | Medium | Sprint 2 auth is critical; warn in onboarding |

---

## What's NOT on This Roadmap (and Why)

- **SSE real-time updates** — APScheduler refreshes every 10 min, sufficient for MVP
- **Admin endpoints** — Developer-only monitoring, not user-facing
- **Landscape orientation** — Mobile news readers used in portrait 95%+ of the time
- **Custom app icon** — Cosmetic, zero impact on product value
- **Multi-language** — English-only MVP is appropriate for initial user base
