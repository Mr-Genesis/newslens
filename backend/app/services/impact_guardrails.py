"""Impact-engine guardrails (Wave A · IMPACT_ENGINE_SPEC §7).

Pure functions — unit-testable without an LLM. They run AFTER Pydantic validation and
BEFORE caching. ``lint_no_advice`` is the one hard *safety* rule (no buy/sell/hold/etc. on
the money dimension); the rest clean or flag.

Token matching is whole-word/phrase only (``\\b``-anchored regex). Substring matching would
false-positive on household / shareholder / shortage / shortly — see test_impact_guardrails.
"""
import re

ADVICE_TOKENS = [
    "buy", "sell", "hold", "short", "allocate", "overweight", "underweight",
    "you should", "target price", "price target", "will rise", "will fall",
]
HYPE_TOKENS = ["game-changer", "game changer", "revolutionary", "massive"]


def _matches(text: str, tokens: list[str]) -> list[str]:
    if not text:
        return []
    low = text.lower()
    return [t for t in tokens if re.search(r"\b" + re.escape(t) + r"\b", low)]


def lint_no_advice(financial: dict | None) -> list[str]:
    """Advice-token violations in the financial dimension's free text (empty = clean)."""
    if not financial or not financial.get("applicable"):
        return []
    fields = [financial.get("relevance", ""), financial.get("mechanism", "")]
    fields += list(financial.get("watch_items", []) or [])
    out: list[str] = []
    for f in fields:
        out += _matches(f, ADVICE_TOKENS)
    return sorted(set(out))


def lint_groundedness(impact: dict, source_outlets: list[str]) -> dict:
    """Drop any evidence whose source isn't among the provided outlets. Mutates + returns."""
    allowed = {o.strip().lower() for o in (source_outlets or [])}
    for dim in (impact.get("dimensions") or {}).values():
        if not isinstance(dim, dict):
            continue
        dim["evidence"] = [
            e for e in (dim.get("evidence") or [])
            if isinstance(e, dict) and e.get("source", "").strip().lower() in allowed
        ]
    return impact


def enforce_honesty(impact: dict) -> dict:
    """applicable:true with empty relevance → downgrade to applicable:false. Mutates + returns."""
    for dim in (impact.get("dimensions") or {}).values():
        if isinstance(dim, dict) and dim.get("applicable") and not (dim.get("relevance") or "").strip():
            dim["applicable"] = False
    return impact


def detect_hype(impact: dict) -> list[str]:
    """Hype tokens anywhere in the impact's free text → caller regenerates (no raw deletion)."""
    out: list[str] = []
    pr = impact.get("personal_relevance") or {}
    out += _matches(pr.get("one_liner", ""), HYPE_TOKENS)
    out += _matches(impact.get("headline", ""), HYPE_TOKENS)
    out += _matches(impact.get("caveats", ""), HYPE_TOKENS)
    for dim in (impact.get("dimensions") or {}).values():
        if not isinstance(dim, dict):
            continue
        out += _matches(dim.get("relevance", ""), HYPE_TOKENS)
        out += _matches(dim.get("mechanism", ""), HYPE_TOKENS)
        for w in (dim.get("watch_items") or []):
            out += _matches(w, HYPE_TOKENS)
    return sorted(set(out))
