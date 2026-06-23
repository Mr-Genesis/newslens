"""E4 integration: hybrid search (keyword ranks above semantic-only)."""
import pytest

from app.config import settings
from app.models import Article, EmbeddingStatus, Source, SourceType


async def _article(db_session, src, title, url, embedding):
    a = Article(
        title=title, url=url, source_id=src.id, embedding=embedding,
        embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(a)
    await db_session.flush()
    return a


@pytest.mark.asyncio
async def test_keyword_ranks_above_semantic_only(aclient, db_session, fake_llm):
    src = Source(name="S", url="https://s.example/se", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    dim = settings.embedding_dimensions
    near = [0.0] * dim
    near[0] = 1.0  # matches fake query embedding [1,0,...]
    far = [0.0] * dim
    far[1] = 1.0
    await _article(db_session, src, "Reliance earnings beat estimates", "https://s.example/kw", far)
    await _article(db_session, src, "Tata quarterly report", "https://s.example/sem", near)

    r = await aclient.get("/search?q=Reliance")
    assert r.status_code == 200
    titles = [x["title"] for x in r.json()["results"]]
    assert "Reliance earnings beat estimates" in titles
    assert titles.index("Reliance earnings beat estimates") < titles.index("Tata quarterly report")


@pytest.mark.asyncio
async def test_search_empty_query_rejected(aclient, db_session):
    r = await aclient.get("/search?q=")
    assert r.status_code in (400, 422)
