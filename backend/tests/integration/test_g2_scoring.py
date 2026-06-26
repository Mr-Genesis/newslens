"""G2 S5: the shared per-cluster relevance scorer consumed by feed / briefing / search."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Article, ArticleEntity, ClusterArticle, EmbeddingStatus, Entity, Source, SourceType,
    StoryCluster, User, UserEntityRelevance,
)
from app.services import entities as E

_n = 0


async def _ensure_user1(db):
    if (await db.execute(select(User).where(User.id == 1))).scalar_one_or_none() is None:
        db.add(User(id=1, locale="IN"))
        await db.flush()


async def _cluster_with_entities(db, *salience_by_name):
    """A cluster with one article carrying the given (entity_name, salience) pairs. Returns (cluster, {name: Entity})."""
    global _n
    _n += 1
    src = Source(name="S", url=f"https://sc/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    art = Article(title="A", url=f"https://sc/{_n}/a", source_id=src.id,
                  embedding_status=EmbeddingStatus.complete)
    db.add(art)
    await db.flush()
    cl = StoryCluster(title="C")
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    ents = {}
    for name, sal in salience_by_name:
        _n += 1
        e = Entity(canonical_name=name, name_norm=f"{name.lower()}-{_n}", kind="org")
        db.add(e)
        await db.flush()
        db.add(ArticleEntity(article_id=art.id, entity_id=e.id, salience=sal))
        ents[name] = e
    await db.flush()
    return cl, ents


def _uer(uid, entity, *, weight=1.0, when=None):
    return UserEntityRelevance(user_id=uid, entity_id=entity.id, source="follow",
                               engagement_raw=weight,
                               last_event_at=when or datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_scorer_empty_fastpaths(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    cl, _ = await _cluster_with_entities(db_session, ("X", 0.5))
    monkeypatch.setattr(s, "uer_enabled", False)
    assert await E.score_clusters_relevance(db_session, [cl.id], 1) == {}  # off
    monkeypatch.setattr(s, "uer_enabled", True)
    assert await E.score_clusters_relevance(db_session, [cl.id], None) == {}  # no user
    assert await E.score_clusters_relevance(db_session, [], 1) == {}  # no ids


@pytest.mark.asyncio
async def test_scorer_zero_uer_user_is_noop(db_session, monkeypatch):
    """A user with no follows/feedback scores 0.0 everywhere — the surface no-op invariant
    (salience is deliberately NOT in the surface score, so popularity can't reorder a no-signal user)."""
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    cl, _ = await _cluster_with_entities(db_session, ("Alpha", 0.9), ("Beta", 0.2))
    scores = await E.score_clusters_relevance(db_session, [cl.id], 1)
    assert scores.get(cl.id, 0.0) == 0.0


@pytest.mark.asyncio
async def test_scorer_followed_entity_lifts_cluster(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    cl_followed, ents = await _cluster_with_entities(db_session, ("Followed", 0.5))
    cl_plain, _ = await _cluster_with_entities(db_session, ("Plain", 0.5))
    db_session.add(_uer(1, ents["Followed"]))
    await db_session.flush()
    scores = await E.score_clusters_relevance(db_session, [cl_followed.id, cl_plain.id], 1)
    assert scores.get(cl_followed.id, 0.0) > scores.get(cl_plain.id, 0.0)
    assert scores.get(cl_plain.id, 0.0) == 0.0


@pytest.mark.asyncio
async def test_scorer_decay_fresh_over_stale(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    cl_fresh, ef = await _cluster_with_entities(db_session, ("Fresh", 0.5))
    cl_stale, es = await _cluster_with_entities(db_session, ("Stale", 0.5))
    now = datetime.now(timezone.utc)
    db_session.add_all([
        _uer(1, ef["Fresh"], when=now),
        _uer(1, es["Stale"], when=now - timedelta(days=120)),
    ])
    await db_session.flush()
    scores = await E.score_clusters_relevance(db_session, [cl_fresh.id, cl_stale.id], 1)
    assert scores[cl_fresh.id] > scores[cl_stale.id] > 0


@pytest.mark.asyncio
async def test_scorer_future_timestamp_clamped(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    cl, e = await _cluster_with_entities(db_session, ("Future", 0.5))
    db_session.add(_uer(1, e["Future"], when=datetime.now(timezone.utc) + timedelta(days=365)))
    await db_session.flush()
    score = (await E.score_clusters_relevance(db_session, [cl.id], 1))[cl.id]
    assert 0 < score <= 1.0  # decay clamped to <= 1; without the clamp this would explode


@pytest.mark.asyncio
async def test_scorer_batch_ranks_by_engagement(db_session, monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s, "uer_enabled", True)
    await _ensure_user1(db_session)
    cl1, e1 = await _cluster_with_entities(db_session, ("E1", 0.5))
    cl2, e2 = await _cluster_with_entities(db_session, ("E2", 0.5))
    cl3, _ = await _cluster_with_entities(db_session, ("E3", 0.5))  # no follow → absent/0
    now = datetime.now(timezone.utc)
    db_session.add_all([_uer(1, e1["E1"], weight=2.0, when=now), _uer(1, e2["E2"], weight=1.0, when=now)])
    await db_session.flush()
    scores = await E.score_clusters_relevance(db_session, [cl1.id, cl2.id, cl3.id], 1)
    assert scores[cl1.id] > scores[cl2.id] > scores.get(cl3.id, 0.0)
    # single-cluster wrapper agrees with the batch form
    assert await E.score_cluster_relevance(db_session, cl1.id, 1) == pytest.approx(scores[cl1.id])
