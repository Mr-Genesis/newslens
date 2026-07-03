"""Root route + HTML-entity hygiene + current Gemini generation model.

Covers the three prod issues found after the Gemini cutover: GET / 404-noise, raw HTML entities
(&nbsp; &#8377;) surfacing in snippets/summaries, and the retired gemini-2.0-flash model default.
"""
import html

import pytest

from app.config import Settings


# ── GET / ──

@pytest.mark.asyncio
async def test_root_route_returns_service_info(client):
    r = await client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "NewsLens API"
    assert body["health"] == "/health"
    assert body["docs"] == "/docs"


# ── generation model default ──

def test_gemini_generation_model_is_current(monkeypatch):
    """gemini-2.0-flash was retired (404 NotFound in prod — same vector as text-embedding-004).
    Guard the shipped default so a revert reintroducing the dead model fails loudly."""
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert Settings().gemini_model == "gemini-2.5-flash"


# ── entity decoding at ingestion (the exact transform the fetcher applies) ──

def test_strip_tags_then_unescape_never_yields_live_tags():
    """Order matters: strip tags FIRST, then unescape — otherwise encoded '&lt;script&gt;'
    would decode into a live tag after the strip already ran."""
    import re

    raw = "&lt;script&gt;alert(1)&lt;/script&gt; RBI auction &nbsp;&#8377;34,000 crore &amp; more"
    out = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
    assert "₹34,000" in out          # &#8377; → ₹
    assert "&nbsp;" not in out and "&amp;" not in out
    assert "<script>" in out              # decoded but INERT text — strip already ran, never executed
    # and a real tag in the source is removed before decoding
    raw2 = "<p>Sensex up &nbsp;500 points</p>"
    out2 = html.unescape(re.sub(r"<[^>]+>", "", raw2)).strip()
    assert "<p>" not in out2 and "500 points" in out2 and "&nbsp;" not in out2


@pytest.mark.asyncio
async def test_summarizer_fallback_unescapes_entities(monkeypatch):
    """Rows ingested before the fetcher fix still hold raw entities — the summary fallback
    must decode them so degraded cards render clean."""
    from app.services import llm, summarizer

    async def _unavailable(*a, **k):
        raise llm.LLMUnavailable("no key")

    monkeypatch.setattr(llm, "generate", _unavailable)

    headline, summary, coherence = await summarizer.generate_cluster_summary(
        ["RBI auction"], ["&nbsp;Cut-off yield &#8377;34,000 crore. Second sentence here."],
    )
    assert headline is None  # LLM unavailable → keep the existing cluster title
    assert coherence == 0.70
    assert "&#8377;" not in summary and "&nbsp;" not in summary
    assert "₹" in summary
