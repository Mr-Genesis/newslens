"""Embeddings run on Gemini (text-embedding-004, 768-dim, task-typed) — not OpenAI."""
from app.config import settings
from app.services import embeddings


def test_embedding_config_is_gemini():
    assert settings.embedding_model == "models/gemini-embedding-001"
    assert settings.embedding_dimensions == 768
    assert settings.embedding_task_document == "retrieval_document"
    assert settings.embedding_task_query == "retrieval_query"


def _patch_gemini(monkeypatch, captured):
    import google.generativeai as genai

    def _configure(api_key=None):
        captured["key"] = api_key

    def _embed(model=None, content=None, task_type=None, output_dimensionality=None):
        captured.update(
            model=model, content=content, task_type=task_type, output_dim=output_dimensionality
        )
        return {"embedding": [0.1, 0.2, 0.3]}

    monkeypatch.setattr(genai, "configure", _configure)
    monkeypatch.setattr(genai, "embed_content", _embed)


async def _fake_key():
    return "test-gemini-key"


async def test_generate_embedding_calls_gemini_document(monkeypatch):
    cap = {}
    _patch_gemini(monkeypatch, cap)
    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _fake_key)

    out = await embeddings.generate_embedding("hello world")

    assert out == [0.1, 0.2, 0.3]
    assert cap["key"] == "test-gemini-key"
    assert cap["model"] == "models/gemini-embedding-001"
    assert cap["content"] == "hello world"
    assert cap["task_type"] == "retrieval_document"  # stored-document default
    assert cap["output_dim"] == 768                  # truncated to the pgvector column size


async def test_query_embedding_uses_query_task_type(monkeypatch):
    cap = {}
    _patch_gemini(monkeypatch, cap)
    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _fake_key)
    embeddings._query_embedding_cache.clear()

    out = await embeddings.embed_query_cached("budget news")

    assert out == [0.1, 0.2, 0.3]
    assert cap["task_type"] == "retrieval_query"  # asymmetric retrieval for search queries


async def test_generate_embedding_no_key_returns_none(monkeypatch):
    async def _no_key():
        return None

    monkeypatch.setattr(embeddings, "_resolve_embedding_key", _no_key)
    assert await embeddings.generate_embedding("x") is None
