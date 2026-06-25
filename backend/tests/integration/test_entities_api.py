"""G1 S1-S2: the cast-strip + 'appears in' read endpoints (pure SQL, real DB harness)."""
from datetime import datetime, timezone

import pytest

from app.models import (
    Article, ArticleEntity, ClusterArticle, EmbeddingStatus, Entity, EntityAlias, Source,
    SourceType, StoryCluster,
)
from app.services import entities as E

_n = 0


async def _src(db):
    global _n
    _n += 1
    s = Source(name="S", url=f"https://ge/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _article(db, src):
    global _n
    _n += 1
    a = Article(title="A", url=f"https://ge/{_n}/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    return a


async def _cluster(db, *articles, title="C", created_at=None):
    cl = StoryCluster(title=title)
    if created_at is not None:
        cl.created_at = created_at
    db.add(cl)
    await db.flush()
    for a in articles:
        db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return cl


async def _entity(db, name, kind="org"):
    e = Entity(canonical_name=name, name_norm=name.lower(), kind=kind)
    db.add(e)
    await db.flush()
    return e


@pytest.mark.asyncio
async def test_cluster_entities_dedup_order_cap(aclient, db_session):
    src = await _src(db_session)
    a1, a2 = await _article(db_session, src), await _article(db_session, src)
    cl = await _cluster(db_session, a1, a2)
    e_high = await _entity(db_session, "Reserve Bank")
    e_mid = await _entity(db_session, "Finance Ministry")
    e_low = await _entity(db_session, "Some Bank")
    db_session.add_all([
        ArticleEntity(article_id=a1.id, entity_id=e_high.id, salience=0.6),  # same entity, two
        ArticleEntity(article_id=a2.id, entity_id=e_high.id, salience=0.9),  # articles → dedup to max
        ArticleEntity(article_id=a1.id, entity_id=e_mid.id, salience=0.5),
        ArticleEntity(article_id=a1.id, entity_id=e_low.id, salience=0.2),
    ])
    await db_session.flush()

    body = (await aclient.get(f"/clusters/{cl.id}/entities")).json()
    names = [e["canonical_name"] for e in body]
    assert names[0] == "Reserve Bank"            # highest salience (max 0.9) first
    assert names.count("Reserve Bank") == 1      # deduped across articles
    sal = [e["salience"] for e in body]
    assert sal == sorted(sal, reverse=True)      # ordered desc
    assert set(body[0].keys()) == {"id", "canonical_name", "kind", "salience"}


@pytest.mark.asyncio
async def test_entity_clusters_recency_and_absence(aclient, db_session):
    src = await _src(db_session)
    e = await _entity(db_session, "Acme Corp")
    other = await _entity(db_session, "Unrelated")
    a_old = await _article(db_session, src)
    a_new = await _article(db_session, src)
    a_other = await _article(db_session, src)
    await _cluster(db_session, a_old, title="Older", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    await _cluster(db_session, a_new, title="Newer", created_at=datetime(2026, 6, 20, tzinfo=timezone.utc))
    await _cluster(db_session, a_other, title="Other", created_at=datetime(2026, 6, 25, tzinfo=timezone.utc))
    db_session.add_all([
        ArticleEntity(article_id=a_old.id, entity_id=e.id, salience=0.8),
        ArticleEntity(article_id=a_new.id, entity_id=e.id, salience=0.7),
        ArticleEntity(article_id=a_other.id, entity_id=other.id, salience=0.9),  # different entity
    ])
    await db_session.flush()

    body = (await aclient.get(f"/entities/{e.id}/clusters")).json()
    titles = [c["title"] for c in body]
    assert titles == ["Newer", "Older"]   # newest-first, and "Other" (E not mentioned) absent


@pytest.mark.asyncio
async def test_resolve_existing_by_name_and_alias(db_session):
    e = await _entity(db_session, "Reserve Bank")
    db_session.add(EntityAlias(entity_id=e.id, alias="RBI", alias_norm="rbi"))
    await db_session.flush()
    assert await E.resolve_existing(db_session, "Reserve Bank") == e.id  # exact name
    assert await E.resolve_existing(db_session, "rbi") == e.id            # alias, case-insensitive
    assert await E.resolve_existing(db_session, "Nope") is None


@pytest.mark.asyncio
async def test_entity_follow_creation_succeeds(aclient, db_session):
    await _entity(db_session, "Acme")
    r = await aclient.post("/follows", json={"kind": "entity", "value": "Acme"})
    assert r.status_code == 201  # the S7 resolution hook runs without breaking follow creation
