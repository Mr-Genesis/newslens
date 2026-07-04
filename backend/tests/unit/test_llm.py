"""Unit tests for the LLM generation seam (E1/E★). Pure/native — no DB, no network."""
import pytest

from app.services import llm


class TestExtractJson:
    def test_plain_json(self):
        assert llm.extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json_block(self):
        assert llm.extract_json('```json\n{"a": 1, "b": [2, 3]}\n```') == {"a": 1, "b": [2, 3]}

    def test_prose_wrapped_json(self):
        assert llm.extract_json('Sure! {"a": 1} — hope that helps.') == {"a": 1}

    def test_array_root(self):
        assert llm.extract_json("[1, 2, 3]") == [1, 2, 3]

    def test_passthrough_when_already_parsed(self):
        assert llm.extract_json({"a": 1}) == {"a": 1}

    def test_unparseable_raises(self):
        with pytest.raises(ValueError):
            llm.extract_json("there is no json here at all")


@pytest.mark.asyncio
class TestGenerateRouting:
    @pytest.fixture(autouse=True)
    def _provider_from_env(self, monkeypatch):
        # Wave E: generate() resolves the provider via _active_settings (a cached DB read). These
        # branch tests intend to drive it off settings.generation_provider, so route it there
        # directly (no cache, no DB) — active-settings resolution is covered by its own tests.
        from app.config import settings as _s

        async def _fake(user_id=None):
            return ((_s.generation_provider or "openai").lower(), {})

        monkeypatch.setattr(llm, "_active_settings", _fake)

    async def test_routes_to_gemini(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "generation_provider", "gemini")
        called = {}

        async def fake_gemini(prompt, **kw):
            called["gemini"] = True
            return "G"

        async def fake_openai(prompt, **kw):
            called["openai"] = True
            return "O"

        monkeypatch.setattr(llm, "_generate_gemini", fake_gemini)
        monkeypatch.setattr(llm, "_generate_openai", fake_openai)
        out = await llm.generate("hi")
        assert out == "G"
        assert called == {"gemini": True}

    async def test_routes_to_openai_by_default(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "generation_provider", "openai")

        async def fake_gemini(prompt, **kw):
            return "G"

        async def fake_openai(prompt, **kw):
            return "O"

        monkeypatch.setattr(llm, "_generate_gemini", fake_gemini)
        monkeypatch.setattr(llm, "_generate_openai", fake_openai)
        assert await llm.generate("hi") == "O"

    async def test_unavailable_when_no_openai_key(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "generation_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "")
        import app.services.embeddings as emb

        async def none_client(user_id=None):
            return None

        monkeypatch.setattr(emb, "_get_client_async", none_client)
        with pytest.raises(llm.LLMUnavailable):
            await llm.generate("hi")

    async def test_generate_routes_to_provider(self, monkeypatch):
        # generate() dispatches on settings.generation_provider, defaulting to openai.
        from app.config import settings
        seen = {}

        async def fake_gemini(prompt, **kw):
            seen["provider"] = "gemini"
            return "G"

        async def fake_openai(prompt, **kw):
            seen["provider"] = "openai"
            return "O"

        monkeypatch.setattr(llm, "_generate_gemini", fake_gemini)
        monkeypatch.setattr(llm, "_generate_openai", fake_openai)

        monkeypatch.setattr(settings, "generation_provider", "gemini")
        assert await llm.generate("hi") == "G"
        assert seen["provider"] == "gemini"

        monkeypatch.setattr(settings, "generation_provider", "openai")
        assert await llm.generate("hi") == "O"
        assert seen["provider"] == "openai"

        # Unknown / empty provider falls back to openai.
        monkeypatch.setattr(settings, "generation_provider", "")
        assert await llm.generate("hi") == "O"
        assert seen["provider"] == "openai"


@pytest.mark.asyncio
async def test_generate_no_key_returns_unavailable(monkeypatch):
    # No usable key for the configured provider → LLMUnavailable (callers map to "unavailable").
    from app.config import settings
    monkeypatch.setattr(settings, "generation_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "")

    async def no_gem_key(user_id=None):
        return None

    monkeypatch.setattr(llm, "_resolve_gemini_key", no_gem_key)
    with pytest.raises(llm.LLMUnavailable):
        await llm.generate("hi")


def test_json_repair_recovers_wrapped_json():
    # extract_json must recover JSON wrapped in a markdown ```json code fence.
    fenced = '```json\n{"verdict": "ok", "items": [1, 2, 3]}\n```'
    assert llm.extract_json(fenced) == {"verdict": "ok", "items": [1, 2, 3]}
    # Bare triple-backtick fence (no language tag) also works.
    assert llm.extract_json('```\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.asyncio
async def test_gemini_key_cache_slot_separate_from_openai(monkeypatch):
    # The Gemini key cache is its own module-level slot; it must not be polluted by
    # or shared with the OpenAI client path. Resolving the Gemini key falls back to
    # the env key and caches it independently.
    from app.config import settings
    monkeypatch.setattr(settings, "gemini_api_key", "gem-env-key")
    # OpenAI key set to a different value to prove the slots don't cross-contaminate.
    monkeypatch.setattr(settings, "openai_api_key", "sk-openai-key")

    # Reset the Gemini cache (WS-6: now a per-user dict) so the fallback path runs deterministically.
    llm._gem_key_cache.clear()

    from app.services.auth import current_user_id
    key = await llm._resolve_gemini_key()
    assert key == "gem-env-key"
    # The dedicated Gemini cache holds the Gemini key for the default user, not the OpenAI one.
    assert llm._gem_key_cache[current_user_id()][0] == "gem-env-key"
    assert llm._gem_key_cache[current_user_id()][0] != settings.openai_api_key


@pytest.mark.asyncio
async def test_fake_llm_seam_returns_injected(monkeypatch):
    # Unit-level proof of the generate() seam: monkeypatch it and assert the injected
    # value comes back with no network call.
    async def fake_generate(prompt, **kw):
        return "INJECTED"

    monkeypatch.setattr(llm, "generate", fake_generate)
    assert await llm.generate("anything") == "INJECTED"
