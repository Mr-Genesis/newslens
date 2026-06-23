"""Wave B2: framework registry — auto-selection + brevity (pure, no LLM/DB). TDD."""
from app.services import frameworks as F


def test_select_caps_at_4():
    sel = F.select_frameworks("markets")
    assert len(sel) <= 4
    assert all("id" in f and "label" in f for f in sel)


def test_select_by_story_type():
    geo = {f["id"] for f in F.select_frameworks("geopolitics")}
    assert "game_theory" in geo  # game-theory fires on geopolitics
    mkt = {f["id"] for f in F.select_frameworks("markets")}
    assert mkt and mkt <= {f["id"] for f in F.FRAMEWORKS}


def test_select_general_nonempty():
    assert len(F.select_frameworks("general")) >= 1


def test_infer_story_type():
    assert F.infer_story_type(["World", "Geopolitics"]) == "geopolitics"
    assert F.infer_story_type(["Markets", "Business"]) == "markets"
    assert F.infer_story_type(["Technology", "AI"]) == "tech"
    assert F.infer_story_type([]) == "general"


def test_clamp_words():
    long = " ".join(["w"] * 30)
    assert len(F.clamp_words(long, 20).split()) == 20
    assert F.clamp_words("short line", 20) == "short line"
