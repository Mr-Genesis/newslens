"""Wave B2: the presentation-framework registry + auto-selection + brevity.

Pure functions (no LLM/DB) so selection and the <=20-word budget are unit-testable. The
one-liner generation + caching lives in lenses.frameworks.
"""

# id, label, and the story types it auto-fires on. The surface is capped at 4
# (select_frameworks), in registry priority order — so order matters here.
FRAMEWORKS = [
    {"id": "base_rate", "label": "Base rate",
     "fires": ["markets", "tech", "science", "geopolitics", "general"]},
    {"id": "second_order", "label": "2nd-order",
     "fires": ["markets", "tech", "policy", "general"]},
    {"id": "game_theory", "label": "Game theory",
     "fires": ["geopolitics"]},
    {"id": "incentives", "label": "Incentives",
     "fires": ["policy", "markets", "geopolitics"]},
    {"id": "signal_noise", "label": "Signal vs noise",
     "fires": ["markets", "tech", "breaking", "general"]},
    {"id": "steelman", "label": "Steelman",
     "fires": ["policy", "geopolitics", "general"]},
    {"id": "precedent", "label": "Precedent",
     "fires": ["geopolitics", "policy", "general"]},
    {"id": "bayesian", "label": "Bayesian update",
     "fires": ["breaking", "science", "general"]},
    {"id": "reflexivity", "label": "Reflexivity",
     "fires": ["markets"]},
]

# Guardrail note per framework (forecast/analogy frameworks must bite back). Used in the prompt.
GUARDRAILS = {
    "base_rate": "state the reference class; flag if n is small",
    "game_theory": "emit a falsifiable condition + confidence + horizon; never zero-sum by default",
    "precedent": "ALWAYS include the disanalogy, not just the analogy",
    "bayesian": "qualitative bands only — no false precision",
}

_BY_ID = {f["id"]: f for f in FRAMEWORKS}

_STORY_TYPE_TERMS = {
    "geopolitics": ("world", "geopolitics", "international", "politics", "conflict", "defense", "war"),
    "markets": ("markets", "business", "finance", "economy", "stocks", "trade"),
    "tech": ("technology", "tech", "ai", "software", "startup"),
    "policy": ("policy", "regulation", "law", "government", "election"),
    "science": ("science", "health", "research", "climate", "medicine"),
}


def infer_story_type(topic_names: list[str]) -> str:
    names = [n.lower() for n in (topic_names or []) if n]
    for stype, terms in _STORY_TYPE_TERMS.items():
        if any(term in name for name in names for term in terms):
            return stype
    return "general"


def select_frameworks(story_type: str, cap: int = 4) -> list[dict]:
    """Frameworks that auto-fire for this story type, in registry priority order, capped."""
    return [
        {"id": f["id"], "label": f["label"]}
        for f in FRAMEWORKS
        if story_type in f["fires"]
    ][:cap]


def clamp_words(text: str, n: int = 20) -> str:
    words = (text or "").split()
    return text if len(words) <= n else " ".join(words[:n])
