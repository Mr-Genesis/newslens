"""WS-5 (#115): one-hop interest expansion in score_clusters_relevance — a bounded adjacency nudge
that is a strict no-op for a zero-signal user (the G2 invariant) and when the flag is off."""
from datetime import datetime, timezone

import pytest

from app.models import (
    Article, ArticleEntity, ClusterArticle, Entity, EntityEdge, Source, SourceType, StoryCluster,
    User, UserEntityRelevance,
)
from app.services import entities

UTC = timezone.utc
_n = 0


async def _ensure_user(db, uid=1):
    if await db.get(User, uid) is None:
        db.add(User(id=uid, locale="IN"))
        await db.flush()


async def _entity(db, name):
    global _n
    _n += 1
    e = Entity(canonical_name=f"{name}{_n}", name_norm=f"{name}{_n}".lower(), kind="org")
    db.add(e)
    await db.flush()
    return e


async def _cluster_with(db, ents):
    global _n
    _n += 1
    src = Source(name="S", url=f"https://x/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    art = Article(title=f"a{_n}", url=f"https://x/{_n}/a", source_id=src.id, published_at=datetime.now(UTC))
    db.add(art)
    await db.flush()
    c = StoryCluster(title=f"c{_n}")
    db.add(c)
    await db.flush()
    db.add(ClusterArticle(cluster_id=c.id, article_id=art.id))
    for e in ents:
        db.add(ArticleEntity(article_id=art.id, entity_id=e.id, salience=0.5))
    await db.flush()
    return c


async def _follow(db, uid, entity, raw=1.0):
    db.add(UserEntityRelevance(user_id=uid, entity_id=entity.id, source="follow",
                               engagement_raw=raw, last_event_at=datetime.now(UTC)))
    await db.flush()


@pytest.mark.asyncio
async def test_expansion_boosts_an_adjacent_cluster(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    monkeypatch.setattr(s, "expansion_enabled", True)
    await _ensure_user(db_session)
    a, b = await _entity(db_session, "A"), await _entity(db_session, "B")
    await _follow(db_session, 1, a)                                   # user has affinity for A only
    db_session.add(EntityEdge(src_entity_id=a.id, dst_entity_id=b.id, weight=1.0))  # A—B adjacency
    await db_session.flush()
    cl = await _cluster_with(db_session, [b])                          # a cluster of ONLY B

    scores = await entities.score_clusters_relevance(db_session, [cl.id], 1)
    assert scores.get(cl.id, 0.0) > 0.0                               # adjacency lifted a no-direct-signal cluster
    assert scores[cl.id] <= s.expansion_weight + 1e-9                 # bounded to at most expansion_weight


@pytest.mark.asyncio
async def test_expansion_off_leaves_adjacent_cluster_at_zero(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    monkeypatch.setattr(s, "expansion_enabled", False)
    await _ensure_user(db_session)
    a, b = await _entity(db_session, "A"), await _entity(db_session, "B")
    await _follow(db_session, 1, a)
    db_session.add(EntityEdge(src_entity_id=a.id, dst_entity_id=b.id, weight=1.0))
    await db_session.flush()
    cl = await _cluster_with(db_session, [b])

    scores = await entities.score_clusters_relevance(db_session, [cl.id], 1)
    assert scores.get(cl.id, 0.0) == 0.0  # no direct affinity for B + expansion off → base 0.0


@pytest.mark.asyncio
async def test_expansion_is_noop_for_zero_signal_user(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    monkeypatch.setattr(s, "expansion_enabled", True)
    await _ensure_user(db_session)
    a, b = await _entity(db_session, "A"), await _entity(db_session, "B")
    db_session.add(EntityEdge(src_entity_id=a.id, dst_entity_id=b.id, weight=1.0))
    await db_session.flush()
    cl = await _cluster_with(db_session, [b])  # user has NO UER → no seeds → no expansion

    scores = await entities.score_clusters_relevance(db_session, [cl.id], 1)
    assert scores.get(cl.id, 0.0) == 0.0  # zero-signal user unaffected by the graph
