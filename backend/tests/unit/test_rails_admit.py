"""WS-2 (#112): the precision guard — the load-bearing decision that keeps "US Iran war" from
dragging in every Middle-East story. Pure function, exhaustively tested."""
from app.config import settings
from app.services.rails import _admit, _escape_like


def test_tight_pure_semantic_admits_without_keyword():
    # A very close vector match needs no proper-noun confirmation.
    assert _admit(settings.rails_dist_tight - 0.01, keyword_hit=False, entity_hit=False, semantic_available=True) is True


def test_loose_needs_keyword_or_entity_confirmation():
    d = (settings.rails_dist_tight + settings.rails_dist_loose) / 2  # between tight and loose
    assert _admit(d, keyword_hit=False, entity_hit=False, semantic_available=True) is False   # near but unconfirmed
    assert _admit(d, keyword_hit=True, entity_hit=False, semantic_available=True) is True      # keyword confirms
    assert _admit(d, keyword_hit=False, entity_hit=True, semantic_available=True) is True      # entity confirms


def test_far_never_admits_even_with_keyword():
    assert _admit(settings.rails_dist_loose + 0.1, keyword_hit=True, entity_hit=True, semantic_available=True) is False


def test_no_distance_falls_back_to_keyword_or_entity_only_when_semantic_unavailable():
    # semantic leg unavailable (embeddings down) → a proper-noun hit alone admits
    assert _admit(None, keyword_hit=True, entity_hit=False, semantic_available=False) is True
    assert _admit(None, keyword_hit=False, entity_hit=True, semantic_available=False) is True
    assert _admit(None, keyword_hit=False, entity_hit=False, semantic_available=False) is False


def test_keyword_or_entity_hit_outside_ann_topk_is_NOT_admitted_when_semantic_ran():
    # The HIGH-severity bug the review caught: when the semantic leg RAN successfully, a candidate
    # with no distance is one that fell outside the ANN top-k — it was NOT near enough, so a bare
    # keyword/entity hit must NOT admit it (else "US Iran war" pulls in every entity-tagged story).
    assert _admit(None, keyword_hit=True, entity_hit=False, semantic_available=True) is False
    assert _admit(None, keyword_hit=False, entity_hit=True, semantic_available=True) is False
    assert _admit(None, keyword_hit=True, entity_hit=True, semantic_available=True) is False


def test_escape_like_neutralizes_wildcards():
    # A saved-search phrase with % or _ must match LITERALLY, not as a SQL wildcard.
    assert _escape_like("100% pure") == "100\\% pure"
    assert _escape_like("a_b") == "a\\_b"
    assert _escape_like("c:\\path") == "c:\\\\path"  # backslash escaped first
    assert _escape_like("plain") == "plain"
