"""Persona gating: free-text profession → audience tags (Phase 1)."""
from app.services.audience import tags_for_profession


def test_doctor_maps_to_medicine():
    assert "medicine" in tags_for_profession("Cardiologist")
    assert "medicine" in tags_for_profession("Doctor (MBBS)")


def test_ml_engineer_maps_to_ai_and_software():
    tags = tags_for_profession("Machine Learning Engineer")
    assert "ai" in tags and "software" in tags


def test_finance_and_law():
    assert "finance" in tags_for_profession("Equity trader, CFA")
    assert "law" in tags_for_profession("Advocate, High Court")


def test_no_profession_is_empty():
    assert tags_for_profession(None) == set()
    assert tags_for_profession("") == set()


def test_unmatched_profession_is_empty():
    # A profession with no domain keyword gets no tags → gated sources stay hidden.
    assert tags_for_profession("Poet") == set()


def test_engineer_reaches_engineering_and_technology_sources():
    # IEEE Spectrum is tagged audience=["engineering","technology"]; an engineer must be able to
    # see it, so the profession must produce at least one of those tags.
    tags = tags_for_profession("Hardware Engineer")
    assert tags & {"engineering", "technology"}
