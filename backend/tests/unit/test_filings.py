"""Phase 3 — India exchange filings: pure helpers (name matching, company parsing).

The NSE per-company feeds carry the company only as a full legal name in <title> (no symbol/
scrip anywhere), so ONE normalization key (`norm_company`) is the canonical thing the ingest
filter, the entity alias, and the read-path all key on. If these three ever computed the key
differently a watchlisted filing would be ingested-but-invisible (or vice-versa), so the key
lives in exactly one function and is tested here.
"""
from types import SimpleNamespace

from app.services.filings import filing_company_name, norm_company


def test_norm_company_strips_legal_suffix_and_case():
    # The load-bearing invariant: the full legal name and the bare name collapse to ONE key, so a
    # user who watchlists "Reliance Industries" matches a feed <title> of "Reliance Industries Limited".
    assert norm_company("Reliance Industries Limited") == "reliance industries"
    assert norm_company("Reliance Industries") == "reliance industries"
    assert norm_company("RELIANCE INDUSTRIES LTD.") == "reliance industries"


def test_norm_company_handles_punctuation_and_whitespace():
    assert norm_company("Dr. Lal Path Labs Ltd.") == "dr lal path labs"
    assert norm_company("  Tata   Consultancy   Services  ") == "tata consultancy services"
    assert norm_company("D.K. Enterprises Global Limited") == "dk enterprises global"


def test_norm_company_empty_or_suffix_only_is_empty():
    # Empty / whitespace / a bare suffix must never produce a key — else every feed item with no
    # real name would collide on "" and leak to anyone whose watchlist normalized to "".
    assert norm_company("") == ""
    assert norm_company("   ") == ""
    assert norm_company("Limited") == ""
    assert norm_company(None) == ""


# ── filing_company_name: pull the verbatim company name out of a feed entry ──
def test_filing_company_name_nse_uses_title_verbatim():
    # NSE per-company feeds put the clean full legal name in <title>; the raw name (not the norm key)
    # is returned so it can become the entity's display canonical_name.
    e = SimpleNamespace(title="Dr. Lal Path Labs Ltd.", link="https://nsearchives.../IT_1.xml")
    assert filing_company_name(e, "nse_name") == "Dr. Lal Path Labs Ltd."


def test_filing_company_name_none_when_empty_or_unusable():
    assert filing_company_name(SimpleNamespace(title="   "), "nse_name") is None
    assert filing_company_name(SimpleNamespace(), "nse_name") is None
    # A name that normalizes to nothing (bare suffix) is not a real company → None, so the ingest
    # filter never tries to match or attach an empty-key entity.
    assert filing_company_name(SimpleNamespace(title="Limited"), "nse_name") is None
