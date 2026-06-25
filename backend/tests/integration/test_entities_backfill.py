"""G1 S5-S6: decoupled backfill job (settled + on-change) + platform-key seam."""
import contextlib

import pytest
from sqlalchemy import func, select

from app.models import (
    Article, ArticleEntity, ClusterArticle, EmbeddingStatus, Entity, Source, SourceType, StoryCluster,
)

_n = 0


async def _src(db):
    global _n
    _n += 1
    s = Source(name="S", url=f"https://bf/{_n}", source_type=SourceType.wire)
    db.add(s)
    await db.flush()
    return s


async def _article(db, src):
    global _n
    _n += 1
    a = Article(title="T", snippet="s", extracted_text="full body about the central bank and a city",
                url=f"https://bf/{_n}/a", source_id=src.id, embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    return a


async def _cluster(db, *arts, title="C"):
    cl = StoryCluster(title=title, summary="x")
    db.add(cl)
    await db.flush()
    for a in arts:
        db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return cl


def _route_session_to_test(monkeypatch, db_session):
    from app.services import entities as E

    @contextlib.asynccontextmanager
    async def _fake():
        yield db_session  # don't close the shared session on exit

    monkeypatch.setattr(E, "async_session", _fake)


@pytest.mark.asyncio
async def test_backfill_extracts_settled_ignores_unsettled(fake_llm, db_session, monkeypatch):
    from app.config import settings as s
    from app.services import entities as E

    monkeypatch.setattr(s, "graph_extraction_enabled", True)
    _route_session_to_test(monkeypatch, db_session)

    src = await _src(db_session)
    a1, a2 = await _article(db_session, src), await _article(db_session, src)
    await _cluster(db_session, a1, a2)            # settled (2 sources) → extracted
    a3 = await _article(db_session, src)
    await _cluster(db_session, a3)                # unsettled (1 source) → ignored

    await E.backfill_entities()

    assert fake_llm["generate"] == 1             # only the settled cluster called the LLM
    settled = (await db_session.execute(select(func.count()).select_from(ArticleEntity).where(
        ArticleEntity.article_id.in_([a1.id, a2.id])))).scalar()
    unsettled = (await db_session.execute(select(func.count()).select_from(ArticleEntity).where(
        ArticleEntity.article_id == a3.id))).scalar()
    assert settled > 0 and unsettled == 0


@pytest.mark.asyncio
async def test_backfill_skips_unchanged(fake_llm, db_session, monkeypatch):
    from app.config import settings as s
    from app.services import entities as E, lenses

    monkeypatch.setattr(s, "graph_extraction_enabled", True)
    _route_session_to_test(monkeypatch, db_session)

    src = await _src(db_session)
    a1, a2 = await _article(db_session, src), await _article(db_session, src)
    cl = await _cluster(db_session, a1, a2)
    _, articles = await lenses._load(db_session, cl.id)
    sh = lenses._source_hash(articles)
    await lenses._cache_write(db_session, cl, "extra_json", "graph", sh, {"entities": 0})  # already done

    await E.backfill_entities()

    assert fake_llm["generate"] == 0             # unchanged → no LLM call
    assert (await db_session.execute(select(func.count()).select_from(ArticleEntity))).scalar() == 0


@pytest.mark.asyncio
async def test_force_platform_key_bypasses_user_key(monkeypatch):
    """S6: extraction's force_platform_key uses the platform/env key, never the owner's per-user key."""
    from app.services import embeddings, llm

    class _Resp:
        class _Choice:
            class _Msg:
                content = '{"entities": []}'
            message = _Msg()
        choices = [_Choice()]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    return _Resp()

    used = {"user": 0, "platform": 0}

    async def spy_user():
        used["user"] += 1
        return "USER-KEY"

    def spy_platform():
        used["platform"] += 1
        return _Client()

    monkeypatch.setattr(embeddings, "_get_user_api_key", spy_user)
    monkeypatch.setattr(embeddings, "_get_client_platform", spy_platform)

    out = await llm._generate_openai("p", schema={"x": 1}, force_platform_key=True)
    assert used["platform"] == 1 and used["user"] == 0
    assert out == {"entities": []}
