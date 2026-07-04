"""WS-2 (#112): the precision guard — the load-bearing decision that keeps "US Iran war" from
dragging in every Middle-East story. Pure function, exhaustively tested."""
from app.config import settings
from app.services.rails import _admit


def test_tight_pure_semantic_admits_without_keyword():
    # A very close vector match needs no proper-noun confirmation.
    assert _admit(settings.rails_dist_tight - 0.01, keyword_hit=False, entity_hit=False) is True


def test_loose_needs_keyword_or_entity_confirmation():
    d = (settings.rails_dist_tight + settings.rails_dist_loose) / 2  # between tight and loose
    assert _admit(d, keyword_hit=False, entity_hit=False) is False   # semantically near but unconfirmed
    assert _admit(d, keyword_hit=True, entity_hit=False) is True     # keyword confirms
    assert _admit(d, keyword_hit=False, entity_hit=True) is True     # entity confirms


def test_far_never_admits_even_with_keyword():
    assert _admit(settings.rails_dist_loose + 0.1, keyword_hit=True, entity_hit=True) is False


def test_no_distance_falls_back_to_keyword_or_entity():
    # semantic leg unavailable (embeddings down) → a proper-noun hit alone admits
    assert _admit(None, keyword_hit=True, entity_hit=False) is True
    assert _admit(None, keyword_hit=False, entity_hit=True) is True
    assert _admit(None, keyword_hit=False, entity_hit=False) is False
