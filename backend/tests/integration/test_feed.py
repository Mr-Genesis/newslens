"""E0: /feed must report real source_count + cluster_id (multi-source visible)."""
import pytest

from app.models import (
    Article,
    ClusterArticle,
    EmbeddingStatus,
    Source,
    SourceType,
    StoryCluster,
)


async def _seed(db_session):
    src = Source(name="Src", url="https://x.example/feed-src", source_type=SourceType.wire)
    db_session.add(src)
    await db_session.flush()
    arts = []
    for i in range(3):
        a = Article(
            title=f"Clustered {i}", url=f"https://x.example/c{i}",
            source_id=src.id, embedding_status=EmbeddingStatus.complete,
        )
        db_session.add(a)
        arts.append(a)
    standalone = Article(
        title="Standalone", url="https://x.example/solo",
        source_id=src.id, embedding_status=EmbeddingStatus.complete,
    )
    db_session.add(standalone)
    cl = StoryCluster(title="Big story", summary="A real summary exists")
    db_session.add(cl)
    await db_session.flush()
    for a in arts:
        db_session.add(ClusterArticle(cluster_id=cl.id, article_id=a.id))
    await db_session.flush()
    return cl, arts, standalone


@pytest.mark.asyncio
async def test_feed_reports_real_source_count_and_cluster(aclient, db_session):
    cl, _arts, _standalone = await _seed(db_session)
    resp = await aclient.get("/feed?per_page=50")
    assert resp.status_code == 200
    items = {it["title"]: it for it in resp.json()["articles"]}

    c0 = items["Clustered 0"]
    assert c0["source_count"] == 3
    assert c0["cluster_id"] == cl.id
    assert c0["has_ai_summary"] is True

    s = items["Standalone"]
    assert s["source_count"] == 1
    assert s["cluster_id"] is None
    assert s["has_ai_summary"] is False
