"""Wave E S5+S6: graph extraction is provider-aware (never sends a gpt-* id to Claude) and skips
gracefully when the active provider has no key."""
import pytest

from app.services import entities as E
from app.services import llm


class _Cluster:
    id = 1
    title = "t"


@pytest.mark.asyncio
async def test_extraction_uses_active_provider_model_not_hardcoded_gpt(monkeypatch):
    async def _active(user_id=None):
        return ("anthropic", {})
    monkeypatch.setattr(llm, "_active_settings", _active)
    monkeypatch.setattr(llm.settings, "anthropic_model", "claude-haiku-4-5")
    cap = {}

    async def _spy(prompt, **kw):
        cap["model"] = kw.get("model")
        return {"entities": []}

    monkeypatch.setattr(llm, "_generate_anthropic", _spy)
    await E.extract_entities(_Cluster(), [])
    assert cap["model"].startswith("claude") and "gpt" not in cap["model"]


@pytest.mark.asyncio
async def test_extraction_skips_on_no_key(monkeypatch):
    async def _boom(*a, **k):
        raise llm.LLMUnavailable("no key for active provider")

    monkeypatch.setattr(llm, "generate", _boom)
    out = await E.extract_entities(_Cluster(), [])
    assert out is None  # graceful skip, not a crash
