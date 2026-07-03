"""#95 — the verified-spare expert sources are seeded, valid, and audience-reachable."""
from app.services.audience import _KEYWORDS
from app.services.fetcher import load_feeds

PRODUCIBLE = set(_KEYWORDS)  # tags tags_for_profession can actually emit
SPARES = {
    "Chartbook", "Silver Bulletin", "Lenny's Newsletter", "ChinaTalk", "Volts",
    "The Diff", "India Uncut", "Kyla's Newsletter", "Strange Loop Canon",
}


def test_spare_experts_seeded_valid_and_reachable():
    by_name = {f["name"]: f for f in load_feeds()}
    seeded = SPARES & set(by_name)
    assert len(seeded) >= 8, f"expected the verified spares seeded, found {sorted(seeded)}"
    for name in seeded:
        f = by_name[name]
        assert f["source_type"] == "expert"
        assert isinstance(f.get("credibility_score"), int) and 0 <= f["credibility_score"] <= 100
        assert (f.get("credibility_meta") or {}).get("rationale"), f"{name} needs a rationale"
        aud = set(f.get("audience") or [])
        assert aud and aud <= PRODUCIBLE, f"{name} audience {aud} not all emittable"


def test_all_gated_sources_have_a_valid_credibility_score():
    for f in load_feeds():
        if f["source_type"] in ("research", "expert"):
            s = f.get("credibility_score")
            assert isinstance(s, int) and 0 <= s <= 100, f"{f['name']} has invalid score {s}"
