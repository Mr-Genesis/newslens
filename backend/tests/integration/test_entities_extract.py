"""G1 S3-S4 (integration): extract → resolve → persist; idempotent; alias reuse."""
import pytest
from sqlalchemy import func, select

from app.models import (
    Article, ArticleEntity, ClusterArticle, EmbeddingStatus, Entity, EntityAlias, Source,
    SourceType, StoryCluster,
)
from app.schemas import EntityExtraction, ExtractedEntity
from app.services import entities as E

_n = 0


async def _cluster_with_article(db):
    global _n
    _n += 1
    src = Source(name="S", url=f"https://ex/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    art = Article(title="T", snippet="s", extracted_text="full body about the central bank",
                  url=f"https://ex/{_n}/a", source_id=src.id, embedding_status=EmbeddingStatus.complete)
    db.add(art)
    await db.flush()
    cl = StoryCluster(title="C", summary="S")
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db.flush()
    return cl, art


@pytest.mark.asyncio
async def test_extract_then_persist_then_idempotent(fake_llm, db_session):
    cl, art = await _cluster_with_article(db_session)
    ext = await E.extract_entities(cl, [art])
    assert ext is not None and len(ext.entities) == 2  # fake_llm returns RBI + Geneva

    await E.resolve_and_persist(db_session, [art], ext)
    n_ent = (await db_session.execute(select(func.count()).select_from(Entity))).scalar()
    n_link = (await db_session.execute(select(func.count()).select_from(ArticleEntity))).scalar()
    assert n_ent == 2 and n_link == 2

    await E.resolve_and_persist(db_session, [art], ext)  # re-run is a no-op
    assert (await db_session.execute(select(func.count()).select_from(Entity))).scalar() == 2
    assert (await db_session.execute(select(func.count()).select_from(ArticleEntity))).scalar() == 2


@pytest.mark.asyncio
async def test_alias_resolution_reuses_existing_entity(fake_llm, db_session):
    cl, art = await _cluster_with_article(db_session)
    e = Entity(canonical_name="Reserve Bank", name_norm="reserve bank", kind="org")
    db_session.add(e)
    await db_session.flush()
    db_session.add(EntityAlias(entity_id=e.id, alias="RBI", alias_norm="rbi"))
    await db_session.flush()

    # extracted canonical "RBI" matches the existing alias → reuse, don't create a second node
    ext = EntityExtraction(entities=[ExtractedEntity(canonical_name="RBI", kind="org", salience=0.9)])
    await E.resolve_and_persist(db_session, [art], ext)

    assert (await db_session.execute(select(func.count()).select_from(Entity))).scalar() == 1
    links = (await db_session.execute(
        select(ArticleEntity).where(ArticleEntity.entity_id == e.id))).scalars().all()
    assert len(links) == 1


@pytest.mark.asyncio
async def test_salience_floor_drops_low_entities(fake_llm, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "graph_salience_floor", 0.7)  # Geneva (0.5) should be dropped
    cl, art = await _cluster_with_article(db_session)
    ext = await E.extract_entities(cl, [art])
    await E.resolve_and_persist(db_session, [art], ext)
    names = [r[0] for r in (await db_session.execute(select(Entity.canonical_name))).all()]
    assert "Reserve Bank of India" in names and "Geneva" not in names
