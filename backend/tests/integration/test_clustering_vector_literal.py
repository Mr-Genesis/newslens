"""Regression: clustering fed pgvector `str(article.embedding)`, but a pgvector column round-trips
as a numpy ndarray whose str() is SPACE-separated ('[0.1 0.2 ...]') — which pgvector rejects with a
syntax error. That crashed _find_nearest_cluster on the first article every run → 0 clusters ever →
every story stuck on the 'still being processed' placeholder. The literal must be comma-separated.

In-session ORM tests missed this because the object keeps the original list (comma str); only a real
DB read returns the ndarray — so these tests use a real numpy array, the exact prod condition.
"""
import numpy as np
import pytest

from app.services import clustering, embeddings


def test_vector_literal_is_comma_separated_for_numpy():
    lit = embeddings.vector_literal(np.array([0.1, 0.2, 0.3], dtype=float))
    assert lit.startswith("[") and lit.endswith("]")
    assert "," in lit and " " not in lit          # commas, NO spaces (pgvector parse)
    assert "..." not in lit                        # numpy truncation must never leak in
    # round-trips to 3 values
    assert lit.count(",") == 2


def test_vector_literal_handles_plain_list_too():
    assert embeddings.vector_literal([0.1, 0.2]) == "[0.1,0.2]"


def test_vector_literal_full_dim_has_no_ellipsis():
    lit = embeddings.vector_literal(np.array([0.0123] * 768, dtype=float))
    assert "..." not in lit
    assert lit.count(",") == 767                   # all 768 components present, none elided


@pytest.mark.asyncio
async def test_find_nearest_cluster_does_not_crash_on_numpy_embedding(db_session):
    """The exact prod path: _find_nearest_cluster receives an article whose embedding is a numpy
    array. It must run the pgvector query WITHOUT a PostgresSyntaxError and return None when there
    are no clusters — instead of raising and aborting the whole clustering run."""
    from types import SimpleNamespace

    art = SimpleNamespace(embedding=np.array([0.01] * 768, dtype=float))
    result = await clustering._find_nearest_cluster(art)  # pre-fix: raises PostgresSyntaxError
    assert result is None
