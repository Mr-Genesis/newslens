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

        async def none_client():
            return None

        monkeypatch.setattr(emb, "_get_client_async", none_client)
        with pytest.raises(llm.LLMUnavailable):
            await llm.generate("hi")
