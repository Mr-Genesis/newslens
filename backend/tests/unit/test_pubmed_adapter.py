"""Phase 3 · #86 — PubMed E-utilities adapter (esearch → PMIDs, efetch → title+abstract)."""
import pytest

from app.services import pubmed


class _FakeResponse:
    def __init__(self, *, json_data=None, text=None):
        self._json = json_data
        self.text = text or ""

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class _FakeClient:
    """Records the last URL/params and returns a queued canned response."""
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params or {}})
        return self._response


_ESEARCH_JSON = {"esearchresult": {"idlist": ["40000001", "40000002", "40000003"]}}

_EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle><MedlineCitation>
    <PMID>40000001</PMID>
    <Article>
      <ArticleTitle>A cardiology trial</ArticleTitle>
      <Abstract><AbstractText Label="BACKGROUND">First part.</AbstractText>
      <AbstractText Label="RESULTS">Second part.</AbstractText></Abstract>
    </Article>
  </MedlineCitation></PubmedArticle>
  <PubmedArticle><MedlineCitation>
    <PMID>40000002</PMID>
    <Article><ArticleTitle>No abstract paper</ArticleTitle></Article>
  </MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


def test_term_for_profession_maps_specialties():
    assert pubmed.term_for_profession("Cardiologist") == "cardiology"
    assert pubmed.term_for_profession("Doctor (MBBS)") == "medicine"   # generic medical fallback
    assert pubmed.term_for_profession("Software Engineer") is None      # non-medical → no PubMed
    assert pubmed.term_for_profession(None) is None


@pytest.mark.asyncio
async def test_esearch_parses_idlist_and_sends_api_key():
    client = _FakeClient(_FakeResponse(json_data=_ESEARCH_JSON))
    ids = await pubmed.esearch(client, "cardiology", reldate=7, api_key="KEY123", retmax=25)
    assert ids == ["40000001", "40000002", "40000003"]
    params = client.calls[0]["params"]
    assert params["term"] == "cardiology" and params["reldate"] == 7
    assert params["datetype"] == "edat" and params["api_key"] == "KEY123"


@pytest.mark.asyncio
async def test_efetch_parses_title_and_joined_abstract():
    client = _FakeClient(_FakeResponse(text=_EFETCH_XML))
    items = await pubmed.efetch(client, ["40000001", "40000002"], api_key=None)
    by_pmid = {i["pmid"]: i for i in items}
    assert by_pmid["40000001"]["title"] == "A cardiology trial"
    assert "First part." in by_pmid["40000001"]["abstract"]
    assert "Second part." in by_pmid["40000001"]["abstract"]  # multi-section joined
    # A paper with no abstract still returns (abstract empty) — the caller decides whether to keep it.
    assert by_pmid["40000002"]["abstract"] == ""
