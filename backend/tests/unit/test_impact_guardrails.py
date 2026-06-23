"""Wave A: impact guardrail lints + StoryImpact schema validity (pure, no LLM/DB)."""
import pytest
from pydantic import ValidationError

from app.schemas import StoryImpact
from app.services import impact_guardrails as g


def _fin(text):
    return {"applicable": True, "relevance": text, "mechanism": "", "watch_items": []}


# ── no-advice lint (the hard safety rule) ──
ADVICE_SENTENCES = [
    "You should buy this now.",
    "Time to sell before earnings.",
    "Hold your position.",
    "Go short the index.",
    "Allocate 20% here.",
    "Overweight the sector.",
    "Underweight bonds.",
    "Our price target is 200.",
    "The target price is high.",
    "Shares will rise sharply.",
    "It will fall next week.",
]


@pytest.mark.parametrize("sentence", ADVICE_SENTENCES)
def test_no_advice_catches_each_token(sentence):
    assert g.lint_no_advice(_fin(sentence)), f"missed advice in: {sentence}"


def test_no_advice_clean_passes():
    assert g.lint_no_advice(_fin("Exposure via the supply chain; watch demand.")) == []


def test_no_advice_false_positive_guard():
    # whole-word matching: advice substrings that are NOT advice must not fire
    for s in [
        "Household budgets tighten.",
        "Shareholder pressure grows.",
        "A chip shortage persists.",
        "We will shortly know more.",
        "A stronghold of demand.",
    ]:
        assert g.lint_no_advice(_fin(s)) == [], f"false positive on: {s}"


def test_no_advice_skips_inapplicable_and_none():
    assert g.lint_no_advice({"applicable": False, "relevance": "you should buy"}) == []
    assert g.lint_no_advice(None) == []


# ── groundedness / honesty / hype ──
def test_groundedness_drops_unlisted_sources():
    impact = {"dimensions": {"professional": {"evidence": [
        {"claim": "x", "source": "Reuters"}, {"claim": "y", "source": "Bloomberg"}]}}}
    g.lint_groundedness(impact, ["Reuters"])
    assert [e["source"] for e in impact["dimensions"]["professional"]["evidence"]] == ["Reuters"]


def test_enforce_honesty_downgrades_empty_relevance():
    impact = {"dimensions": {"civic": {"applicable": True, "relevance": "   "}}}
    g.enforce_honesty(impact)
    assert impact["dimensions"]["civic"]["applicable"] is False


def test_detect_hype_flags_and_clean():
    dirty = {"headline": "A revolutionary, massive game-changer", "caveats": "",
             "personal_relevance": {"one_liner": ""}, "dimensions": {}}
    hits = g.detect_hype(dirty)
    assert {"revolutionary", "massive", "game-changer"} <= set(hits)
    clean = {"headline": "A measured shift", "caveats": "",
             "personal_relevance": {"one_liner": "calm"}, "dimensions": {}}
    assert g.detect_hype(clean) == []


# ── schema validity (Pydantic is the contract) ──
def _valid():
    return {
        "headline": "h",
        "personal_relevance": {"score": 50, "one_liner": "o"},
        "dimensions": {
            "professional": {"applicable": True},
            "financial": {"applicable": False},
            "civic": {"applicable": False},
        },
    }


def test_storyimpact_valid_passes():
    StoryImpact.model_validate(_valid())


@pytest.mark.parametrize("score", [101, -1, 1000])
def test_storyimpact_rejects_out_of_range_score(score):
    bad = _valid()
    bad["personal_relevance"]["score"] = score
    with pytest.raises(ValidationError):
        StoryImpact.model_validate(bad)


def test_storyimpact_requires_personal_relevance():
    with pytest.raises(ValidationError):
        StoryImpact.model_validate({"headline": "h", "dimensions": {}})


def test_storyimpact_rejects_bad_enum():
    bad = _valid()
    bad["dimensions"]["professional"]["horizon"] = "someday"
    with pytest.raises(ValidationError):
        StoryImpact.model_validate(bad)
