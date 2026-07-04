"""Pipeline observability: embedding failures are classified + recorded so /pipeline can surface WHY
the pipeline is stalled (quota vs auth vs no-key vs other) without needing the Render log stream."""
import pytest

from app.services import embeddings


def test_classify_embedding_error_categories():
    c = embeddings._classify_embedding_error
    assert c("429 Resource has been exhausted (quota)") == "quota"
    assert c("Rate limit exceeded, retry later") == "quota"
    assert c("API key not valid. Please pass a valid API key.") == "auth"
    assert c("403 PERMISSION_DENIED") == "auth"
    assert c("401 Unauthenticated") == "auth"
    assert c("Some unexpected transport error") == "other"


@pytest.mark.asyncio
async def test_generate_embedding_records_last_error(monkeypatch):
    """A failing embed call is recorded (category + message) and returns None (never raises)."""
    embeddings._last_embedding_error = None

    async def _fake_key():
        return "fake-key"

    def _boom(*a, **k):
        raise RuntimeError("429 Resource has been exhausted (quota)")

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _fake_key)
    monkeypatch.setattr(embeddings, "_embed_sync", _boom)

    out = await embeddings.generate_embedding("hello world")
    assert out is None
    err = embeddings.last_embedding_error()
    assert err is not None
    assert err["category"] == "quota"
    assert "exhausted" in err["message"].lower()
    assert err.get("when")  # timestamp present


@pytest.mark.asyncio
async def test_generate_embedding_records_no_key(monkeypatch):
    """The silent dead-stop (no Gemini key anywhere) is recorded as its own category."""
    embeddings._last_embedding_error = None

    async def _no_key():
        return None

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _no_key)
    out = await embeddings.generate_embedding("hi")
    assert out is None
    assert embeddings.last_embedding_error()["category"] == "no_key"


@pytest.mark.asyncio
async def test_successful_embedding_clears_last_error(monkeypatch):
    """After a recovery, a success clears the sticky error so /pipeline doesn't cry wolf forever."""
    embeddings._last_embedding_error = {"category": "quota", "message": "old", "when": "x"}

    async def _fake_key():
        return "fake-key"

    def _ok(*a, **k):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _fake_key)
    monkeypatch.setattr(embeddings, "_embed_sync", _ok)

    out = await embeddings.generate_embedding("hi")
    assert out == [0.1, 0.2, 0.3]
    assert embeddings.last_embedding_error() is None
