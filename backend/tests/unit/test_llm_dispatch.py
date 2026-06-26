"""Wave E S1: generate() routes to the active provider + resolves the model (arg → prefs → default)."""
import pytest

from app.services import llm


def _patch_active(monkeypatch, provider, prefs):
    async def _fake():
        return (provider, prefs)
    monkeypatch.setattr(llm, "_active_settings", _fake)


def _spy_anthropic(monkeypatch, captured):
    async def _spy(prompt, **kw):
        captured.update(kw)
        return {"ok": True}
    monkeypatch.setattr(llm, "_generate_anthropic", _spy)


@pytest.mark.asyncio
async def test_generate_routes_to_active_provider(monkeypatch):
    _patch_active(monkeypatch, "anthropic", {})
    cap = {}
    _spy_anthropic(monkeypatch, cap)
    out = await llm.generate("p", schema={"x": 1})
    assert out == {"ok": True}  # reached the anthropic branch


@pytest.mark.asyncio
async def test_model_prefs_override_default(monkeypatch):
    _patch_active(monkeypatch, "anthropic", {"anthropic": "claude-sonnet-4-6"})
    cap = {}
    _spy_anthropic(monkeypatch, cap)
    await llm.generate("p")
    assert cap["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_model_falls_back_to_provider_default(monkeypatch):
    _patch_active(monkeypatch, "anthropic", {})
    monkeypatch.setattr(llm.settings, "anthropic_model", "claude-haiku-4-5")
    cap = {}
    _spy_anthropic(monkeypatch, cap)
    await llm.generate("p")
    assert cap["model"] == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_explicit_model_arg_wins(monkeypatch):
    _patch_active(monkeypatch, "anthropic", {"anthropic": "claude-sonnet-4-6"})
    cap = {}
    _spy_anthropic(monkeypatch, cap)
    await llm.generate("p", model="explicit-model")
    assert cap["model"] == "explicit-model"
