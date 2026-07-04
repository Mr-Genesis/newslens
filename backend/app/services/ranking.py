"""WS-5 (#115): the single home for the FEED ranking blend — recency + entity relevance, nudged by
credibility and specialty. Extracted from routes.get_feed so the formula lives in one tunable,
unit-testable place (a parity test pins it to the original inline behavior).

Scope note: the other surfaces keep their by-design ordering and do NOT consume this blend —
- rails ("News You Follow") are recency-only: the user asked for the latest on a follow, not an
  affinity re-rank;
- the discover deck is randomly sampled (discovery, not ranking);
- the briefing uses its own additive story-weight (topic pref + affinity + field bonus).
So this module is deliberately the feed's blend, ready to be adopted elsewhere in a future A/B.
"""
from app.config import settings


def recency_norm(ts: float | None, lo: float, hi: float) -> float:
    """Publish time normalized to [0,1] over the pool's [lo,hi] range. None → 0.0; a flat pool
    (hi == lo) → 1.0 (matches the original inline guard)."""
    if ts is None:
        return 0.0
    return 1.0 if hi == lo else (ts - lo) / (hi - lo)


def credibility_mult(score: float | None) -> float:
    """#79 bounded ×[0.9, 1.1] nudge. NULL (news) → the neutral default. Clamped to [0,100] at the
    apply point so a bad stored score can never break the bound and drown fresher news."""
    s = settings.credibility_rank_neutral if score is None else score
    s = min(100, max(0, s))
    return 0.9 + 0.2 * s / 100


def specialty_mult(source_specialty: str | None, user_specialty: str | None) -> float:
    """#94 bounded lift when the source's specialty matches the user's own. No specialty on either
    side → ×1.0, so ordinary feeds are unchanged."""
    if not user_specialty or not source_specialty:
        return 1.0
    return settings.specialty_rank_boost if source_specialty == user_specialty else 1.0


def blend_score(
    recency: float, relevance: float, cred: float, specialty: float, ratio: float | None = None
) -> float:
    """The feed blend: (recency vs relevance, mixed by `ratio`) × credibility × specialty. Relevance
    is clamped to [0,1] here (score_clusters_relevance can exceed 1 once expansion is added)."""
    r = settings.uer_feed_blend_ratio if ratio is None else ratio
    return ((1 - r) * recency + r * min(1.0, relevance)) * cred * specialty
