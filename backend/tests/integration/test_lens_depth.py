"""WS-7 (#117): depth_pref threading across the lenses — the retrieval budget scales with depth, the
style suffix is appended, and non-standard depths get a SEPARATE cache subkey (no brief/expert
cross-serve)."""
import pytest

from app.models import Article, ClusterArticle, Source, SourceType, StoryCluster
from app.services import lenses

_n = 0
LONG_BODY = "word " * 6000  # ~30k chars → far exceeds every depth budget


async def _cluster(db):
    global _n
    _n += 1
    src = Source(name=f"Src{_n}", url=f"https://l/{_n}", source_type=SourceType.wire)
    db.add(src)
    await db.flush()
    art = Article(title="T", url=f"https://l/{_n}/a", source_id=src.id, extracted_text=LONG_BODY, snippet="s")
    db.add(art)
    await db.flush()
    c = StoryCluster(title="Story", summary="sum")
    db.add(c)
    await db.flush()
    db.add(ClusterArticle(cluster_id=c.id, article_id=art.id))
    await db.flush()
    return c


def _capture(monkeypatch):
    prompts = []

    async def _gen(prompt, **kw):
        prompts.append(prompt)
        return {"actors": [], "questions": [], "lines": {}, "summary": "", "answer": "",
                "agree_count": 0, "dissent": [], "citations": []}

    monkeypatch.setattr(lenses.llm, "generate", _gen)
    return prompts


@pytest.mark.asyncio
async def test_strategic_depth_scales_budget_appends_suffix_and_scopes_cache(db_session, monkeypatch):
    c = await _cluster(db_session)
    prompts = _capture(monkeypatch)

    await lenses.strategic(db_session, c.id, depth_pref="brief")
    await lenses.strategic(db_session, c.id, depth_pref="expert")

    assert len(prompts) == 2  # distinct cache subkeys ("default" vs "default:expert") → both generate
    brief, expert = prompts
    assert len(expert) > len(brief) + 5000                 # expert budget (16000) >> brief (800)
    assert lenses._depth_suffix("expert") in expert
    assert lenses._depth_suffix("brief") in brief

    # A repeat at the same depth is served from cache (no third generation) — no cross-serve either way.
    await lenses.strategic(db_session, c.id, depth_pref="brief")
    assert len(prompts) == 2


@pytest.mark.asyncio
async def test_consensus_standard_keeps_plain_subkey_for_coherence(db_session, monkeypatch):
    c = await _cluster(db_session)
    _capture(monkeypatch)
    await lenses.consensus(db_session, c.id, depth_pref="standard")
    await db_session.refresh(c)
    assert "consensus" in (c.extra_json or {})  # standard writes the plain slot cluster_coherence reads


@pytest.mark.asyncio
async def test_trivia_depth_scoped_cache_subkey(db_session, monkeypatch):
    c = await _cluster(db_session)
    prompts = _capture(monkeypatch)
    await lenses.trivia(db_session, c.id, "medium", depth_pref="standard")
    await lenses.trivia(db_session, c.id, "medium", depth_pref="expert")
    assert len(prompts) == 2  # "medium" vs "medium:expert" — a brief/standard answer never cross-serves


@pytest.mark.asyncio
async def test_coherence_reads_a_non_standard_depth_consensus(db_session, monkeypatch):
    """Review regression: cluster_coherence reads the plain 'consensus' slot, but a brief/expert user's
    consensus lands under 'consensus:<depth>'. Coherence must fall back to it so the honest agreement
    ratio survives non-standard depth (not silently revert to the source-overlap heuristic)."""
    from sqlalchemy import select

    c = await _cluster(db_session)

    async def _gen(prompt, **kw):
        return {"agree_count": 0, "summary": "", "dissent": []}  # 0 of 1 agree → coherence 0.0

    monkeypatch.setattr(lenses.llm, "generate", _gen)
    await lenses.consensus(db_session, c.id, depth_pref="expert")  # writes "consensus:expert" only
    await db_session.refresh(c)

    arts = (await db_session.execute(
        select(Article).join(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.cluster_id == c.id)
    )).scalars().all()
    coh = lenses.cluster_coherence(c, arts)
    assert coh == 0.0  # used the expert-depth consensus (0/1), NOT the 1-source heuristic (0.65)
