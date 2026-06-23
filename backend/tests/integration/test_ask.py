"""Wave B1 — 'Ask this story': grounded, cited, refusing Q&A. TDD (red first)."""
import pytest

from app.models import (
    Article, ClusterArticle, EmbeddingStatus, Source, SourceType, StoryCluster,
)

_n = 0


async def _seed(db, outlet="Reuters"):
    global _n
    _n += 1
    src = Source(name=outlet, url=f"https://x/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    a = Article(title="EU AI Act", snippet="The EU passed the AI Act.",
                url=f"https://x/{_n}/a", source_id=src.id,
                embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    cl = StoryCluster(title="EU AI Act", summary="The EU passed the AI Act.")
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db.flush()
    return cl


def _patch_llm(monkeypatch, payload, counter=None):
    import app.services.llm as llm

    async def _gen(prompt, *, system=None, schema=None, model=None, max_tokens=None):
        if counter is not None:
            counter["n"] += 1
        return payload

    monkeypatch.setattr(llm, "generate", _gen)


@pytest.mark.asyncio
async def test_ask_returns_grounded_cited_answer(aclient, db_session, monkeypatch):
    cl = await _seed(db_session, "Reuters")
    _patch_llm(monkeypatch, {
        "answer": "The EU passed the AI Act.",
        "citations": [{"claim": "AI Act passed", "source": "Reuters"}],
        "refused": False,
    })
    r = await aclient.post(f"/clusters/{cl.id}/ask", json={"question": "What happened?"})
    assert r.status_code == 200
    b = r.json()
    assert b["refused"] is False
    assert b["answer"]
    assert b["citations"] and b["citations"][0]["source"] == "Reuters"


@pytest.mark.asyncio
async def test_ask_drops_ungrounded_citations(aclient, db_session, monkeypatch):
    cl = await _seed(db_session, "Reuters")
    _patch_llm(monkeypatch, {
        "answer": "Something.",
        "citations": [{"claim": "x", "source": "Bloomberg"}],  # not in the cluster
        "refused": False,
    })
    b = (await aclient.post(f"/clusters/{cl.id}/ask", json={"question": "What?"})).json()
    assert b["citations"] == []  # ungrounded source dropped


@pytest.mark.asyncio
async def test_ask_refused_when_not_in_sources(aclient, db_session, monkeypatch):
    cl = await _seed(db_session)
    _patch_llm(monkeypatch, {"answer": "", "citations": [], "refused": True})
    b = (await aclient.post(f"/clusters/{cl.id}/ask", json={"question": "Who won?"})).json()
    assert b["refused"] is True


@pytest.mark.asyncio
async def test_ask_rejects_empty_question(aclient, db_session):
    cl = await _seed(db_session)
    r = await aclient.post(f"/clusters/{cl.id}/ask", json={"question": "   "})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_ask_rejects_too_long_question(aclient, db_session):
    cl = await _seed(db_session)
    r = await aclient.post(f"/clusters/{cl.id}/ask", json={"question": "x" * 600})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_ask_unavailable_without_key(aclient, db_session):
    # No LLM patch → real seam, no key configured → typed unavailable, never 500.
    cl = await _seed(db_session)
    r = await aclient.post(f"/clusters/{cl.id}/ask", json={"question": "What?"})
    assert r.status_code == 200
    assert r.json().get("unavailable") is True
