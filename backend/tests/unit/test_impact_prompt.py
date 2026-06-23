"""Wave A: the impact prompt actually embeds the persona (deterministic, no LLM).

This is how we test personalization even though the integration fake_llm returns canned
output — we assert the persona reaches the prompt, and persona distinctness is covered by
the cache-hash test in test_impact_v2.
"""
from app.models import StoryCluster
from app.services import lenses


class _Src:
    def __init__(self, name):
        self.name = name
        self.is_paywalled = False


class _Art:
    def __init__(self, title, snippet, src):
        self.title = title
        self.snippet = snippet
        self.source = _Src(src)


def test_impact_user_prompt_embeds_persona():
    persona = {
        "profession": "Nurse",
        "interests": ["Health", "Policy"],
        "watchlist": [{"type": "entity", "value": "NHS"}],
        "country": "GB",
        "region": "London",
        "depth_pref": "expert",
    }
    cl = StoryCluster(id=1, title="Title", summary="Summary text.")
    arts = [_Art("a", "snippet", "Reuters")]
    p = lenses._impact_user(persona, cl, arts, lenses._impact_source_lines(arts))
    for needle in ("Nurse", "Health", "Policy", "NHS", "GB", "London", "expert", "Reuters"):
        assert needle in p, f"persona field missing from prompt: {needle}"


def test_persona_hash_distinct_and_normalized():
    base = {"profession": "Engineer", "interests": ["AI"], "country": "US"}
    same = {"profession": "  engineer ", "interests": ["AI"], "country": "US"}
    diff = {"profession": "Trader", "interests": ["AI"], "country": "US"}
    assert lenses.persona_hash(base) == lenses.persona_hash(same)  # case/whitespace-insensitive
    assert lenses.persona_hash(base) != lenses.persona_hash(diff)
    # a watchlist change yields a different impact
    base2 = {**base, "watchlist": [{"type": "ticker", "value": "NVDA"}]}
    assert lenses.persona_hash(base) != lenses.persona_hash(base2)
