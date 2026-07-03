"""Phase 3 · #87 — interest → arXiv category map + source spec."""
from app.services import arxiv_gen


def test_interests_map_to_arxiv_categories():
    cats = arxiv_gen.arxiv_categories_for_interests(["Computer Vision", "Robotics", "Cooking"])
    assert "cs.CV" in cats and "cs.RO" in cats
    assert "Cooking" not in cats and len(cats) == 2  # unmapped interest adds nothing


def test_arxiv_source_spec_shape():
    spec = arxiv_gen.arxiv_source_spec("cs.CV", ["ai", "technology"])
    assert spec["rss_url"] == "https://rss.arxiv.org/rss/cs.CV"
    assert spec["source_type"] == "research" and spec["is_preprint"] is True
    assert spec["audience"] == ["ai", "technology"] and spec["per_fetch_cap"] == 25
    assert spec["credibility_score"] >= 55  # feed-eligible
