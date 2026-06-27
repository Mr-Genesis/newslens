"""G2 S2-S4: follow→entity persistence + relevance seeding, personalized ranking, feedback + decay."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Article, ArticleEntity, ClusterArticle, EmbeddingStatus, Entity, Follow, Source, SourceType,
    StoryCluster, User, UserEntityRelevance,
)
from app.services import entities as E

_n = 0


async def _ensure_user1(db):
    if (await db.execute(select(User).where(User.id == 1))).scalar_one_or_none() is None:
        db.add(User(id=1, locale="IN"))  # UER.user_id FK target (the default user)
        await db.flush()


async def _src(db):
    global _n
    _n += 1
    s = Source(name="S", url=f"https://g2/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _article(db, src):
    global _n
    _n += 1
    a = Article(title="A", url=f"https://g2/{_n}/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    return a


async def _cluster(db, *arts):
    cl = StoryCluster(title="C")
    db.add(cl)
    await db.flush()
    for a in arts:
        db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return cl


async def _entity(db, name):
    e = Entity(canonical_name=name, name_norm=name.lower(), kind="org")
    db.add(e)
    await db.flush()
    return e


# ── S2 ──
@pytest.mark.asyncio
async def test_entity_follow_persists_entity_id_and_seeds_relevance(aclient, db_session):
    e = await _entity(db_session, "Acme")
    r = await aclient.post("/follows", json={"kind": "entity", "value": "Acme", "entity_id": e.id})
    assert r.status_code == 201
    follow = (await db_session.execute(select(Follow).where(Follow.value == "Acme"))).scalar_one()
    assert follow.entity_id == e.id
    uer = (await db_session.execute(
        select(UserEntityRelevance).where(UserEntityRelevance.entity_id == e.id))).scalar_one()
    assert uer.source == "follow" and uer.engagement_raw == 1.0
    # idempotent re-follow → existing follow returned, no second bump
    await aclient.post("/follows", json={"kind": "entity", "value": "Acme", "entity_id": e.id})
    uer2 = (await db_session.execute(
        select(UserEntityRelevance).where(UserEntityRelevance.entity_id == e.id))).scalar_one()
    assert uer2.engagement_raw == 1.0


@pytest.mark.asyncio
async def test_typed_entity_follow_seeds_relevance(aclient, db_session):
    """A typed entity-follow (no chip id) that resolves to a node still seeds relevance (§2a)."""
    e = await _entity(db_session, "Globex")  # name_norm "globex"
    r = await aclient.post("/follows", json={"kind": "entity", "value": "Globex"})  # no entity_id
    assert r.status_code == 201
    follow = (await db_session.execute(select(Follow).where(Follow.value == "Globex"))).scalar_one()
    assert follow.entity_id is None  # string path leaves the link NULL (resolution is best-effort)
    uer = (await db_session.execute(
        select(UserEntityRelevance).where(UserEntityRelevance.entity_id == e.id))).scalar_one()
    assert uer.source == "follow" and uer.engagement_raw == 1.0


# ── S3 ──
@pytest.mark.asyncio
async def test_cluster_entities_personalized_ranks_followed_first(aclient, db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    a = await _article(db_session, src)
    cl = await _cluster(db_session, a)
    e1 = await _entity(db_session, "Plain")
    e2 = await _entity(db_session, "Followed")
    db_session.add_all([
        ArticleEntity(article_id=a.id, entity_id=e1.id, salience=0.5),
        ArticleEntity(article_id=a.id, entity_id=e2.id, salience=0.5),
    ])
    db_session.add(UserEntityRelevance(user_id=1, entity_id=e2.id, source="follow",
                                       engagement_raw=1.0, last_event_at=datetime.now(timezone.utc)))
    await db_session.flush()
    body = (await aclient.get(f"/clusters/{cl.id}/entities")).json()
    assert body[0]["canonical_name"] == "Followed"  # equal salience → the followed entity ranks first


@pytest.mark.asyncio
async def test_cluster_entities_identical_when_disabled(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", False)  # explicit: the disabled branch, regardless of dev env
    await _ensure_user1(db_session)
    src = await _src(db_session)
    a = await _article(db_session, src)
    cl = await _cluster(db_session, a)
    e_lo = await _entity(db_session, "Lo")
    e_hi = await _entity(db_session, "Hi")
    db_session.add_all([
        ArticleEntity(article_id=a.id, entity_id=e_lo.id, salience=0.2),
        ArticleEntity(article_id=a.id, entity_id=e_hi.id, salience=0.9),
    ])
    db_session.add(UserEntityRelevance(user_id=1, entity_id=e_lo.id, source="follow",
                                       engagement_raw=5.0, last_event_at=datetime.now(timezone.utc)))
    await db_session.flush()
    out = await E.cluster_entities(db_session, cl.id, user_id=1)  # uer_enabled False (default)
    assert [r["canonical_name"] for r in out] == ["Hi", "Lo"]  # pure salience, UER ignored


# ── S4 ──
@pytest.mark.asyncio
async def test_feedback_updates_relevance(aclient, db_session):
    src = await _src(db_session)
    a = await _article(db_session, src)
    e = await _entity(db_session, "Mentioned")
    db_session.add(ArticleEntity(article_id=a.id, entity_id=e.id, salience=0.7))
    await db_session.flush()
    r = await aclient.post("/feedback", json={"article_id": a.id, "feedback_type": "save"})
    assert r.status_code == 201
    uer = (await db_session.execute(
        select(UserEntityRelevance).where(UserEntityRelevance.entity_id == e.id))).scalar_one()
    assert uer.source == "feedback" and uer.engagement_raw == 1.0


@pytest.mark.asyncio
async def test_relevance_decay_on_read(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    a = await _article(db_session, src)
    cl = await _cluster(db_session, a)
    e_old = await _entity(db_session, "Old")
    e_new = await _entity(db_session, "New")
    db_session.add_all([
        ArticleEntity(article_id=a.id, entity_id=e_old.id, salience=0.5),
        ArticleEntity(article_id=a.id, entity_id=e_new.id, salience=0.5),
    ])
    now = datetime.now(timezone.utc)
    db_session.add_all([
        UserEntityRelevance(user_id=1, entity_id=e_old.id, source="follow",
                            engagement_raw=1.0, last_event_at=now - timedelta(days=120)),
        UserEntityRelevance(user_id=1, entity_id=e_new.id, source="follow",
                            engagement_raw=1.0, last_event_at=now),
    ])
    await db_session.flush()
    out = await E.cluster_entities(db_session, cl.id, user_id=1)
    assert out[0]["canonical_name"] == "New"  # fresh engagement decays less → ranks above the stale one


@pytest.mark.asyncio
async def test_future_timestamp_does_not_inflate_rank(db_session, monkeypatch):
    """Clock skew: a last_event_at in the FUTURE must clamp (age>=0, decay<=1), not explode rank."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    a = await _article(db_session, src)
    cl = await _cluster(db_session, a)
    e_future = await _entity(db_session, "Future")  # low salience, but its UER row is future-dated
    e_now = await _entity(db_session, "Now")        # high salience, fresh
    db_session.add_all([
        ArticleEntity(article_id=a.id, entity_id=e_future.id, salience=0.1),
        ArticleEntity(article_id=a.id, entity_id=e_now.id, salience=0.9),
    ])
    now = datetime.now(timezone.utc)
    db_session.add_all([
        UserEntityRelevance(user_id=1, entity_id=e_future.id, source="follow",
                            engagement_raw=1.0, last_event_at=now + timedelta(days=365)),
        UserEntityRelevance(user_id=1, entity_id=e_now.id, source="follow",
                            engagement_raw=1.0, last_event_at=now),
    ])
    await db_session.flush()
    out = await E.cluster_entities(db_session, cl.id, user_id=1)
    # Without the clamp, exp(+huge) would rocket "Future" to the top despite salience 0.1.
    assert out[0]["canonical_name"] == "Now"


@pytest.mark.asyncio
async def test_cluster_entities_tiebreak_is_deterministic(db_session, monkeypatch):
    """Equal-rank entities (common zero-relevance case) must order by a stable key, not heap order."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    src = await _src(db_session)
    a = await _article(db_session, src)
    cl = await _cluster(db_session, a)
    e1 = await _entity(db_session, "Tie one")
    e2 = await _entity(db_session, "Tie two")
    e3 = await _entity(db_session, "Tie three")
    db_session.add_all([
        ArticleEntity(article_id=a.id, entity_id=e1.id, salience=0.5),
        ArticleEntity(article_id=a.id, entity_id=e2.id, salience=0.5),
        ArticleEntity(article_id=a.id, entity_id=e3.id, salience=0.5),
    ])
    await db_session.flush()
    ids = [r["id"] for r in await E.cluster_entities(db_session, cl.id, user_id=1)]
    assert ids == sorted(ids)  # deterministic ascending-id order on equal rank
