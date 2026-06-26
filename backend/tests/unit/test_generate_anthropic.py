"""Wave E S2: _generate_anthropic — content-block join, assistant-prefill JSON, top-level system,
no temperature, max_tokens default, no-key raises. Mocks the anthropic SDK."""
import pytest

from app.services import llm


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, *blocks):
        self.content = list(blocks)


def _mock_client(monkeypatch, captured, *blocks):
    import anthropic

    class _Msgs:
        async def create(self, **kw):
            captured.update(kw)
            return _Resp(*blocks)

    class _Client:
        def __init__(self, api_key=None):
            self.messages = _Msgs()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _Client)


@pytest.mark.asyncio
async def test_schema_path_prefills_and_parses_json(monkeypatch):
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "sk-test")
    cap = {}
    _mock_client(monkeypatch, cap, _Block('"entities": [{"canonical_name":"X","kind":"org","salience":0.9,"aliases":[]}]}'))
    out = await llm._generate_anthropic("p", schema={"e": []}, model="claude-haiku-4-5",
                                        max_tokens=None, force_platform_key=True)
    assert out == {"entities": [{"canonical_name": "X", "kind": "org", "salience": 0.9, "aliases": []}]}
    assert cap["messages"][-1] == {"role": "assistant", "content": "{"}  # prefill present
    assert "temperature" not in cap            # Anthropic: omit temperature
    assert cap["max_tokens"] == 800            # default when None
    assert cap["model"] == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_text_path_joins_blocks_and_top_level_system(monkeypatch):
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "sk-test")
    cap = {}
    _mock_client(monkeypatch, cap, _Block("Hello "), _Block("world"))
    out = await llm._generate_anthropic("p", schema=None, model="m", system="sys", force_platform_key=True)
    assert out == "Hello world"
    assert cap["system"] == "sys"                                    # top-level, not a message
    assert cap["messages"] == [{"role": "user", "content": "p"}]     # no prefill when schema is None


@pytest.mark.asyncio
async def test_no_key_raises(monkeypatch):
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "")

    async def _no_key():
        return None

    monkeypatch.setattr(llm, "_resolve_anthropic_key", _no_key)
    with pytest.raises(llm.LLMUnavailable):
        await llm._generate_anthropic("p", schema={"x": 1}, force_platform_key=False)
