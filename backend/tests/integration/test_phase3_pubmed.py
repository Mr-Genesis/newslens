"""Phase 3 · #86 — PubMed ingestion: profession → specialty research articles, gated + deduped."""
import sqlalchemy as sa

from app.models import Article, Source, SourceType, User
from app.services import pubmed


def _stub_search(pmids):
    async def _s(client, term, **kw):
        return list(pmids)
    return _s


def _stub_fetch(items):
    async def _f(client, pmids, **kw):
        return [i for i in items if i["pmid"] in set(pmids)]
    return _f


async def _set_profession(db_session, profession):
    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = profession
    await db_session.flush()


_PAPER = {"pmid": "40000001", "title": "New cardiology trial",
          "abstract": "A randomized controlled trial with clinically meaningful results here."}


async def test_pubmed_ingest_creates_gated_research_articles(aclient, db_session, monkeypatch):
    await _set_profession(db_session, "Cardiologist")
    monkeypatch.setattr(pubmed, "esearch", _stub_search(["40000001"]))
    monkeypatch.setattr(pubmed, "efetch", _stub_fetch([_PAPER]))

    n = await pubmed.ingest_pubmed(db_session)
    assert n == 1

    art = (await db_session.execute(
        sa.select(Article).where(Article.title == "New cardiology trial"))).scalar_one()
    src = (await db_session.execute(sa.select(Source).where(Source.id == art.source_id))).scalar_one()
    assert src.source_type is SourceType.research
    assert src.audience == ["medicine"] and src.is_preprint is False
    assert art.url == "https://pubmed.ncbi.nlm.nih.gov/40000001/"

    # A cardiologist sees it in the feed (medicine-tagged research clears the gate).
    titles = {a["title"] for a in (await aclient.get("/feed?per_page=50")).json()["articles"]}
    assert "New cardiology trial" in titles


async def test_pubmed_ingest_is_idempotent(db_session, monkeypatch):
    await _set_profession(db_session, "Cardiologist")
    monkeypatch.setattr(pubmed, "esearch", _stub_search(["40000001"]))
    monkeypatch.setattr(pubmed, "efetch", _stub_fetch([_PAPER]))

    await pubmed.ingest_pubmed(db_session)
    await pubmed.ingest_pubmed(db_session)  # same PMID again

    count = (await db_session.execute(
        sa.select(sa.func.count()).select_from(Article).where(
            Article.url == "https://pubmed.ncbi.nlm.nih.gov/40000001/"))).scalar_one()
    assert count == 1  # deduped by PMID


async def test_pubmed_noop_for_non_medical_profession(db_session, monkeypatch):
    await _set_profession(db_session, "Software Engineer")  # no PubMed term
    monkeypatch.setattr(pubmed, "esearch", _stub_search(["40000001"]))
    monkeypatch.setattr(pubmed, "efetch", _stub_fetch([_PAPER]))

    n = await pubmed.ingest_pubmed(db_session)
    assert n == 0
