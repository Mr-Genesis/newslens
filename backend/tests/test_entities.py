"""G1 S3 (unit): EntityExtraction validation — clamp/normalize, reject empties. No DB."""
import pytest
from pydantic import ValidationError

from app.schemas import EntityExtraction


def test_entity_extraction_validates_and_clamps():
    obj = EntityExtraction.model_validate({
        "entities": [
            {"canonical_name": "  Reserve Bank  ", "kind": "ORG", "salience": 1.7, "aliases": ["RBI"]},
            {"canonical_name": "Geneva", "kind": "weird-kind", "salience": -0.2, "aliases": []},
        ]
    })
    assert obj.entities[0].canonical_name == "Reserve Bank"  # stripped
    assert obj.entities[0].kind == "org"                     # lowercased to a known kind
    assert obj.entities[0].salience == 1.0                   # clamped to 1
    assert obj.entities[1].kind == "other"                   # unknown kind → other
    assert obj.entities[1].salience == 0.0                   # clamped to 0


def test_entity_extraction_rejects_empty_name():
    with pytest.raises(ValidationError):
        EntityExtraction.model_validate({"entities": [{"canonical_name": "  ", "kind": "org"}]})


def test_entity_extraction_empty_list_ok():
    assert EntityExtraction.model_validate({"entities": []}).entities == []
