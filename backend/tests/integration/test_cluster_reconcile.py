"""Phase 3 (docs/fixes/follow-rails-identical-rootcause.md): reconcile_clusters merges same-event
clusters that were mis-seeded as parallel singletons. Two-tier guard — a tight pure-semantic centroid
match OR a looser match CONFIRMED by a shared entity/topic. The job is DESTRUCTIVE (reassigns
ClusterArticle → survivor, drops the loser's edges, deletes the loser, clears the survivor's caches),
so cover: the positive merge, the precision reject, the tight-band no-confirmation merge, and the
kill-switch. Routes the job's own async_session() into the test transaction (like test_clustering_*).

All assertions use column selects with ids captured as plain ints BEFORE running the job — never touch
an ORM attribute afterwards, since a post-run expire would trigger a sync lazy-load (MissingGreenlet)."""
import contextlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Article,
    ArticleEntity,
    ClusterArticle,
    EmbeddingStatus,
    Entity,
    Source,
    SourceType,
    StoryCluster,
)

DIM = 768
_seq = 0


def _vec(a: float, b: float) -> list[float]:
    v = [0.0] * DIM
    v[0], v[1] = a, b
    return v


# Unit vectors at a known cosine distance from _V_BASE = _vec(1, 0):
_V_BASE = _vec(1.0, 0.0)
_V_LOOSE = _vec(0.82, 0.5724)   # cos ≈ 0.82 → dist ≈ 0.18 → inside [tight 0.13, loose 0.25)
_V_TIGHT = _vec(0.95, 0.3122)   # cos ≈ 0.95 → dist ≈ 0.05 → below tight


async def _mk_entity(db_session) -> int:
    global _seq
    _seq += 1
    e = Entity(canonical_name=f"Shared {_seq}", name_norm=f"shared-{_seq}", kind="org")
    db_session.add(e)
    await db_session.flush()
    return e.id


async def _mk_cluster(db_session, src_id: int, embedding, *, entity_id: int | None = None) -> tuple[int, int]:
    """One article in its own cluster, seeded with a summary + source_hash so a merge can be shown to
    CLEAR the survivor's caches. Optionally tie the article to `entity_id` (loose-band confirmation).
    Returns (cluster_id, article_id) as plain ints."""
    global _seq
    _seq += 1
    art = Article(
        title=f"seed {_seq}", url=f"https://x.example/reconcile-{_seq}", source_id=src_id,
        embedding_status=EmbeddingStatus.complete, embedding=embedding,
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(art)
    await db_session.flush()
    cl = StoryCluster(title=f"C{_seq}", summary="old summary", source_hash="oldhash")
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    if entity_id is not None:
        db_session.add(ArticleEntity(article_id=art.id, entity_id=entity_id, salience=0.7))
    await db_session.flush()
    return cl.id, art.id


async def _src(db_session, url: str) -> int:
    src = Source(name="R", url=url, source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    return src.id


def _route(monkeypatch, db_session) -> list[int]:
    """Route reconcile's own async_session() to the test transaction, stub schedule_summary, and arm
    the kill-switch ON. Returns the list that captures scheduled survivor ids."""
    from app.config import settings
    from app.services import clustering, summarizer

    @contextlib.asynccontextmanager
    async def _fake():
        yield db_session

    monkeypatch.setattr(clustering, "async_session", _fake)
    scheduled: list[int] = []
    monkeypatch.setattr(summarizer, "schedule_summary", lambda cid: scheduled.append(cid))
    monkeypatch.setattr(settings, "cluster_merge_enabled", True, raising=False)
    return scheduled


async def _cluster_ids(db_session) -> set[int]:
    return set((await db_session.execute(select(StoryCluster.id))).scalars().all())


@pytest.mark.asyncio
async def test_reconcile_merges_loose_band_when_entity_confirms(db_session, monkeypatch):
    from app.services import clustering

    scheduled = _route(monkeypatch, db_session)
    src_id = await _src(db_session, "https://x.example/recon-src1")
    ent_id = await _mk_entity(db_session)
    a_cid, a_aid = await _mk_cluster(db_session, src_id, _V_BASE, entity_id=ent_id)
    b_cid, b_aid = await _mk_cluster(db_session, src_id, _V_LOOSE, entity_id=ent_id)

    await clustering.reconcile_clusters()

    ids = await _cluster_ids(db_session)
    assert b_cid not in ids and a_cid in ids  # survivor = lower id (tie on 1 article each)

    locs = (
        await db_session.execute(
            select(ClusterArticle.cluster_id).where(ClusterArticle.article_id.in_([a_aid, b_aid]))
        )
    ).scalars().all()
    assert set(locs) == {a_cid} and len(locs) == 2  # both articles reassigned to the survivor

    row = (
        await db_session.execute(
            select(StoryCluster.summary, StoryCluster.source_hash).where(StoryCluster.id == a_cid)
        )
    ).first()
    assert row == (None, None)          # survivor caches cleared (its article set changed)
    assert scheduled == [a_cid]         # survivor rescheduled for a fresh summary


@pytest.mark.asyncio
async def test_reconcile_skips_loose_band_without_confirmation(db_session, monkeypatch):
    from app.services import clustering

    scheduled = _route(monkeypatch, db_session)
    src_id = await _src(db_session, "https://x.example/recon-src2")
    a_cid, _ = await _mk_cluster(db_session, src_id, _V_BASE)   # no shared entity/topic
    b_cid, _ = await _mk_cluster(db_session, src_id, _V_LOOSE)

    await clustering.reconcile_clusters()

    ids = await _cluster_ids(db_session)
    assert {a_cid, b_cid} <= ids   # loose band with nothing to confirm → precision guard rejects
    assert scheduled == []


@pytest.mark.asyncio
async def test_reconcile_merges_tight_band_without_confirmation(db_session, monkeypatch):
    from app.services import clustering

    _route(monkeypatch, db_session)
    src_id = await _src(db_session, "https://x.example/recon-src3")
    a_cid, _ = await _mk_cluster(db_session, src_id, _V_BASE)    # no shared entity...
    b_cid, _ = await _mk_cluster(db_session, src_id, _V_TIGHT)   # ...but a very tight centroid match

    await clustering.reconcile_clusters()

    ids = await _cluster_ids(db_session)
    assert (a_cid in ids) ^ (b_cid in ids)  # exactly one survives (tight band auto-merges)


@pytest.mark.asyncio
async def test_reconcile_disabled_is_noop(db_session, monkeypatch):
    from app.config import settings
    from app.services import clustering

    scheduled = _route(monkeypatch, db_session)
    monkeypatch.setattr(settings, "cluster_merge_enabled", False, raising=False)  # kill-switch OFF
    src_id = await _src(db_session, "https://x.example/recon-src4")
    ent_id = await _mk_entity(db_session)
    a_cid, _ = await _mk_cluster(db_session, src_id, _V_BASE, entity_id=ent_id)   # would merge if enabled
    b_cid, _ = await _mk_cluster(db_session, src_id, _V_LOOSE, entity_id=ent_id)

    await clustering.reconcile_clusters()

    ids = await _cluster_ids(db_session)
    assert {a_cid, b_cid} <= ids   # disabled → both clusters remain untouched
    assert scheduled == []
