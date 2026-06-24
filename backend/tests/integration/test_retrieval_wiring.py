"""Wave D1: prove the full body reaches the lenses (not just the headline). TDD."""
import pytest

from app.models import (
    Article, ArticleTopic, ClusterArticle, EmbeddingStatus, Source, SourceType,
    StoryCluster, Topic,
)

_n = 0


async def _seed_with_body(db, body, topic="Markets"):
    global _n
    _n += 1
    src = Source(name="S", url=f"https://rw/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    a = Article(title="Headline only", snippet="short card text", extracted_text=body,
                url=f"https://rw/{_n}/a", source_id=src.id, embedding_status=EmbeddingStatus.complete)
    db.add(a)
    await db.flush()
    cl = StoryCluster(title="C", summary="S")
    db.add(cl)
    await db.flush()
    db.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    t = Topic(name=topic)
    db.add(t)
    await db.flush()
    db.add(ArticleTopic(article_id=a.id, topic_id=t.id, relevance_score=1.0))
    await db.flush()
    return cl


def _capture_llm(monkeypatch, sink):
    import app.services.llm as llm

    async def _gen(prompt, *, system=None, schema=None, model=None, max_tokens=None):
        sink["prompt"] = prompt
        return {"lines": {}}

    monkeypatch.setattr(llm, "generate", _gen)


@pytest.mark.asyncio
async def test_frameworks_prompt_includes_full_body_not_just_headline(aclient, db_session, monkeypatch):
    cl = await _seed_with_body(db_session, "UNIQUEBODYTOKEN " + "x" * 2000)
    sink = {}
    _capture_llm(monkeypatch, sink)
    await aclient.get(f"/clusters/{cl.id}/frameworks")
    # The deep body reached the lens — the Wave D1 depth win — not just title/summary.
    assert "UNIQUEBODYTOKEN" in sink["prompt"]
