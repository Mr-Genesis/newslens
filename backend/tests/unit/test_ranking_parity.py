"""WS-5 (#115): the unified-scorer PARITY guard — the extracted services/ranking.py must reproduce
the ORIGINAL inline feed blend exactly (extracted == inline). Pure functions, no DB."""
import pytest

from app.config import settings
from app.services import ranking


# The formulas exactly as they were inline in routes.get_feed before extraction.
def _inline_cred(score, neutral):
    s = neutral if score is None else score
    s = min(100, max(0, s))
    return 0.9 + 0.2 * s / 100


def _inline_specialty(src, user, boost):
    if not user or not src:
        return 1.0
    return boost if src == user else 1.0


def _inline_recency(ts, lo, hi, span):
    return 0.0 if ts is None else (1.0 if hi == lo else (ts - lo) / span)


def _inline_blend(recency, rel, cred, spec, ratio):
    return ((1 - ratio) * recency + ratio * min(1.0, rel)) * cred * spec


@pytest.mark.parametrize("score", [None, 0, 50, 75, 100, -5, 120])
def test_credibility_mult_parity_and_bounds(score):
    got = ranking.credibility_mult(score)
    assert got == _inline_cred(score, settings.credibility_rank_neutral)
    assert 0.9 <= got <= 1.1  # #79 bound holds even for out-of-range stored scores


@pytest.mark.parametrize(
    "src,user", [(None, None), ("med", None), (None, "med"), ("med", "med"), ("med", "law")]
)
def test_specialty_mult_parity(src, user):
    assert ranking.specialty_mult(src, user) == _inline_specialty(src, user, settings.specialty_rank_boost)


@pytest.mark.parametrize("ts,lo,hi", [(None, 0.0, 10.0), (5.0, 0.0, 10.0), (10.0, 10.0, 10.0), (0.0, 0.0, 10.0)])
def test_recency_norm_parity(ts, lo, hi):
    span = (hi - lo) or 1.0
    assert ranking.recency_norm(ts, lo, hi) == _inline_recency(ts, lo, hi, span)


@pytest.mark.parametrize(
    "recency,rel,cred,spec,ratio",
    [(0.5, 0.2, 1.0, 1.0, 0.3), (1.0, 1.5, 1.1, 1.25, 0.3), (0.0, 0.0, 0.9, 1.0, 0.5), (0.7, 1.0, 1.05, 1.0, 0.9)],
)
def test_blend_score_parity(recency, rel, cred, spec, ratio):
    assert ranking.blend_score(recency, rel, cred, spec, ratio) == _inline_blend(recency, rel, cred, spec, ratio)


def test_blend_default_ratio_matches_config():
    assert ranking.blend_score(0.5, 0.5, 1.0, 1.0) == _inline_blend(0.5, 0.5, 1.0, 1.0, settings.uer_feed_blend_ratio)
