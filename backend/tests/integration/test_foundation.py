"""E★ foundation: prove the pgvector integration harness works end-to-end."""
import pytest
from sqlalchemy import func, select, text

from app.config import settings
from app.models import (
    Article,
    ClusterArticle,
    EmbeddingStatus,
    Source,
    SourceType,
    StoryCluster,
)


@pytest.mark.asyncio
async def test_pgvector_extension_available(db_session):
    v = (
        await db_session.execute(
            text("select extversion from pg_extension where extname='vector'")
        )
    ).scalar()
    assert v is not None


@pytest.mark.asyncio
async def test_create_and_query_cluster(db_session):
    src = Source(
        name="Reuters", url="https://reuters.com/u1", rss_url="https://reuters.com/rss",
        source_type=SourceType.wire, is_paywalled=False,
    )
    db_session.add(src)
    await db_session.flush()
    art = Article(
        title="EU AI Act", snippet="x", url="https://reuters.com/a1",
        source_id=src.id, embedding_status=EmbeddingStatus.pending,
    )
    db_session.add(art)
    await db_session.flush()
    cl = StoryCluster(title="Cluster", summary="s")
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()

    got = (await db_session.execute(select(Article).where(Article.id == art.id))).scalar_one()
    assert got.title == "EU AI Act"
    n = (
        await db_session.execute(
            select(func.count()).select_from(ClusterArticle).where(
                ClusterArticle.cluster_id == cl.id
            )
        )
    ).scalar()
    assert n == 1


@pytest.mark.asyncio
async def test_embedding_column_accepts_vector(db_session):
    src = Source(name="S", url="https://s.example/u2", source_type=SourceType.other)
    db_session.add(src)
    await db_session.flush()
    vec = [0.0] * settings.embedding_dimensions
    vec[0] = 1.0
    art = Article(
        title="V", url="https://s.example/v", source_id=src.id,
        embedding=vec, embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(art)
    await db_session.flush()
    got = (await db_session.execute(select(Article).where(Article.id == art.id))).scalar_one()
    assert got.embedding is not None


@pytest.mark.asyncio
async def test_isolation_rolls_back_between_tests(db_session):
    # Each test's writes are rolled back; the table is empty at the start of every test.
    n = (await db_session.execute(select(func.count()).select_from(Source))).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_fake_llm_seam(fake_llm, db_session):
    from app.services import embeddings, llm
    out = await llm.generate("hi")
    emb = await embeddings.generate_embedding("hi")
    assert out == "STUB SUMMARY"
    assert len(emb) == settings.embedding_dimensions
    assert fake_llm["generate"] == 1 and fake_llm["embed"] == 1
