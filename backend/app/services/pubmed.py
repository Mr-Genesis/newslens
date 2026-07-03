"""Phase 3 · #86 — PubMed E-utilities adapter + per-specialty ingestion.

A doctor's personal research feed. A weekly job maps each active user's profession → a PubMed search
term, calls NCBI E-utilities esearch (last 7 days) → efetch (abstract XML), and ingests each result
as a research Article under a per-specialty research Source (audience=["medicine"]). Those articles
then flow through the existing embedding → clustering → persona-gate pipeline with no new surface.

The session-gated PubMed RSS GUID path (pubmed.ncbi.nlm.nih.gov/rss/search/<GUID>/) 403s for scripts
— this adapter uses the VERIFIED E-utilities JSON/XML endpoints instead. Throttled to ≤3 req/s.
"""
import asyncio
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Article, Source, SourceType, User

logger = structlog.get_logger()

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Medical specialty → PubMed search term. PubMed is a medical database, so only medical professions
# map; everything else returns None (no PubMed feed). Matched as a substring of the profession text.
_PROFESSION_TERMS: dict[str, str] = {
    "cardiolog": "cardiology",
    "oncolog": "oncology",
    "neurolog": "neurology",
    "psychiatr": "psychiatry",
    "radiolog": "radiology",
    "pediatric": "pediatrics",
    "paediatric": "pediatrics",
    "epidemiolog": "epidemiology",
    "dermatolog": "dermatology",
    "endocrinolog": "endocrinology",
    "gastroenterolog": "gastroenterology",
    "nephrolog": "nephrology",
    "pulmonolog": "pulmonology",
    "rheumatolog": "rheumatology",
    "surgeon": "surgery",
    "anesthesiolog": "anesthesiology",
    "anaesthesiolog": "anesthesiology",
    "ophthalmolog": "ophthalmology",
    "obstetric": "obstetrics",
    "gynecolog": "gynecology",
}
_GENERIC_MEDICAL = ("doctor", "physician", "mbbs", "clinician", "medical", "medicine", "nurse")


def term_for_profession(profession: str | None) -> str | None:
    """Map a free-text profession to a PubMed search term (None for non-medical / unset)."""
    if not profession or not profession.strip():
        return None
    text = f" {profession.lower()} "
    for kw, term in _PROFESSION_TERMS.items():
        if kw in text:
            return term
    if any(k in text for k in _GENERIC_MEDICAL):
        return "medicine"
    return None


_last_request = 0.0


async def _rate_limit() -> None:
    """Enforce ≤ 1/interval requests/sec against NCBI (default 0.34s ⇒ ≤3 req/s)."""
    global _last_request
    interval = settings.pubmed_min_request_interval
    if interval <= 0:
        return
    wait = interval - (time.monotonic() - _last_request)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request = time.monotonic()


async def esearch(client: httpx.AsyncClient, term: str, *, reldate: int = 7,
                  api_key: str | None = None, retmax: int = 25) -> list[str]:
    """Return recent PubMed IDs for a term (edat within `reldate` days)."""
    await _rate_limit()
    params = {"db": "pubmed", "term": term, "reldate": reldate, "datetype": "edat",
              "retmode": "json", "retmax": retmax}
    if api_key:
        params["api_key"] = api_key
    resp = await client.get(ESEARCH_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    return list((data or {}).get("esearchresult", {}).get("idlist", []))


def _parse_efetch(xml_text: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("pubmed_efetch_parse_error", error=str(e))
        return items
    for art in root.findall(".//PubmedArticle"):
        pmid_el = art.find(".//PMID")
        pmid = (pmid_el.text or "").strip() if pmid_el is not None else ""
        if not pmid:
            continue
        title_el = art.find(".//ArticleTitle")
        title = (title_el.text or "").strip() if title_el is not None else ""
        parts = ["".join(a.itertext()).strip() for a in art.findall(".//Abstract/AbstractText")]
        abstract = " ".join(p for p in parts if p).strip()
        items.append({"pmid": pmid, "title": title, "abstract": abstract})
    return items


async def efetch(client: httpx.AsyncClient, pmids: list[str], *, api_key: str | None = None) -> list[dict]:
    """Fetch + parse abstracts for a batch of PMIDs → [{pmid, title, abstract}]."""
    if not pmids:
        return []
    await _rate_limit()
    params = {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"}
    if api_key:
        params["api_key"] = api_key
    resp = await client.get(EFETCH_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    return _parse_efetch(resp.text)


async def _ensure_specialty_source(session, term: str) -> Source:
    """Get-or-create the per-specialty PubMed research source (audience-tagged for doctors)."""
    url = f"https://pubmed.ncbi.nlm.nih.gov/?term={term}"
    existing = (await session.execute(select(Source).where(Source.url == url))).scalar_one_or_none()
    if existing is not None:
        return existing
    source = Source(
        name=f"PubMed · {term.title()}", url=url, rss_url=None,
        source_type=SourceType.research, region="global", category="research",
        credibility_score=92, audience=["medicine"], is_preprint=False,
        per_fetch_cap=settings.pubmed_retmax,
        credibility_meta={"reviewed_by": "seed", "note": "PubMed E-utilities specialty feed"},
    )
    session.add(source)
    await session.flush()
    return source


async def ingest_pubmed(session=None) -> int:
    """Weekly job: ingest fresh PubMed abstracts for every medical profession among the users.

    Returns the number of new articles created. Accepts an optional session (tests); otherwise opens
    its own (the scheduler path). No-op when disabled or when no user has a medical profession.
    """
    if not settings.pubmed_enabled:
        logger.info("pubmed_disabled")
        return 0
    if session is not None:
        return await _ingest(session)
    async with async_session() as s:
        return await _ingest(s)


async def _ingest(session) -> int:
    professions = (
        await session.execute(select(User.profession).where(User.profession.isnot(None)))
    ).scalars().all()
    terms = sorted({t for p in professions if (t := term_for_profession(p))})
    if not terms:
        return 0

    api_key = settings.ncbi_api_key or None
    created = 0
    async with httpx.AsyncClient(
        headers={"User-Agent": "NewsLens/0.1 (research feed)"}, follow_redirects=True
    ) as client:
        for term in terms:
            try:
                pmids = await esearch(client, term, reldate=7, api_key=api_key,
                                      retmax=settings.pubmed_retmax)
                results = await efetch(client, pmids, api_key=api_key)
            except httpx.HTTPError as e:
                logger.warning("pubmed_fetch_failed", term=term, error=str(e))
                continue
            if not results:
                continue
            source = await _ensure_specialty_source(session, term)
            for r in results:
                title = (r.get("title") or "").strip()
                if not title:
                    continue
                url = f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/"
                dup = (
                    await session.execute(select(Article.id).where(Article.url == url))
                ).scalar_one_or_none()
                if dup is not None:
                    continue  # dedup by PMID
                abstract = (r.get("abstract") or "").strip()
                session.add(Article(
                    title=title, url=url, source_id=source.id,
                    snippet=abstract[:300] if len(abstract) >= settings.min_snippet_length else None,
                    extracted_text=abstract or None,
                    published_at=datetime.now(timezone.utc),
                ))
                created += 1

    await session.commit()
    logger.info("pubmed_ingest_complete", terms=len(terms), created=created)
    return created
