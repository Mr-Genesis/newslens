"""Wave B3: consensus/divergence — real split + grounded dissent. TDD."""
import pytest

from app.models import (
    Article, ClusterArticle, EmbeddingStatus, Source, SourceType, StoryCluster,
)

_n = 0


async def _seed(db, outlets=("Reuters", "AP")):
    global _n
    _n += 1
    cl = StoryCluster(title="C", summary="Sum.")
    db.add(cl)
    await db.flush()
    for i, o in enumerate(outlets):
        src = Source(name=o, url=f"https://c/{_n}/{i}", source_type=SourceType.wire)
        db.add(src)
        await db.flush()
        a = Article(title="T", snippet="detail", url=f"https://c/{_n}/{i}/a",
                    source_id=src.id, embedding_status=EmbeddingStatus.complete)
        db.add(a)
        await db.flush()
        db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return cl


def _patch(monkeypatch, counter, payload):
    import app.services.llm as llm

    async def _gen(prompt, *, system=None, schema=None, model=None, max_tokens=None):
        counter["n"] += 1
        return payload

    monkeypatch.setattr(llm, "generate", _gen)


@pytest.mark.asyncio
async def test_consensus_returns_split_and_divergence(aclient, db_session, monkeypatch):
    cl = await _seed(db_session, ("Reuters", "AP"))
    _patch(monkeypatch, {"n": 0}, {
        "agree_count": 1,
        "dissent": [{"outlet": "AP", "point": "disputes the parity claim"}],
        "summary": "1 of 2 align",
    })
    b = (await aclient.get(f"/clusters/{cl.id}/consensus")).json()
    assert b["total"] == 2
    assert b["agree_count"] == 1
    assert b["dissent"] and b["dissent"][0]["outlet"] == "AP"
    assert b["summary"]


@pytest.mark.asyncio
async def test_consensus_drops_ungrounded_dissent(aclient, db_session, monkeypatch):
    cl = await _seed(db_session, ("Reuters",))
    _patch(monkeypatch, {"n": 0}, {
        "agree_count": 1,
        "dissent": [{"outlet": "Bloomberg", "point": "x"}],  # not a cluster source
        "summary": "s",
    })
    b = (await aclient.get(f"/clusters/{cl.id}/consensus")).json()
    assert b["dissent"] == []


@pytest.mark.asyncio
async def test_consensus_cached(aclient, db_session, monkeypatch):
    cl = await _seed(db_session, ("Reuters", "AP"))
    c = {"n": 0}
    _patch(monkeypatch, c, {"agree_count": 2, "dissent": [], "summary": "all align"})
    await aclient.get(f"/clusters/{cl.id}/consensus")
    assert c["n"] == 1
    await aclient.get(f"/clusters/{cl.id}/consensus")
    assert c["n"] == 1


@pytest.mark.asyncio
async def test_consensus_unavailable_without_key(aclient, db_session):
    cl = await _seed(db_session)
    b = (await aclient.get(f"/clusters/{cl.id}/consensus")).json()
    assert b.get("unavailable") is True
