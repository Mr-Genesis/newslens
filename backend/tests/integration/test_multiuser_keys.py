"""WS-6 (#116): the multi-user key/provider fix — every per-user resolver keys off the CURRENT
request's user (current_user_id() contextvar), not a hardcoded user #1. Background jobs
(force_platform_key) still use the env key, byte-identical."""
import contextlib

import pytest

from app.models import User, UserSetting
from app.services import embeddings, llm
from app.services.auth import _req_user_id
from app.services.encryption import encrypt_value


def _route_sessions_to_test(monkeypatch, db_session):
    """Make the resolvers' own async_session() yield the test's (uncommitted) session. llm imports it
    lazily from app.database; embeddings holds a module-level ref — patch both."""
    import app.database

    @contextlib.asynccontextmanager
    async def _fake():
        yield db_session

    monkeypatch.setattr(app.database, "async_session", _fake)
    monkeypatch.setattr(embeddings, "async_session", _fake)


async def _seed(db, uid, *, gem, anth, oai, provider):
    if await db.get(User, uid) is None:
        db.add(User(id=uid, locale="IN"))
        await db.flush()
    db.add(
        UserSetting(
            user_id=uid,
            gemini_api_key_encrypted=encrypt_value(gem), gemini_key_verified=True,
            anthropic_api_key_encrypted=encrypt_value(anth), anthropic_key_verified=True,
            openai_api_key_encrypted=encrypt_value(oai), openai_key_verified=True,
            active_provider=provider, model_prefs={provider: f"model-{uid}"},
        )
    )
    await db.flush()


@pytest.fixture(autouse=True)
def _clear_caches():
    for c in (llm._gem_key_cache, llm._anth_key_cache, llm._active_cache, embeddings._user_key_cache):
        c.clear()
    yield
    for c in (llm._gem_key_cache, llm._anth_key_cache, llm._active_cache, embeddings._user_key_cache):
        c.clear()


@pytest.mark.asyncio
async def test_current_user_resolves_own_keys_and_provider_across_all_four_sites(db_session, monkeypatch):
    _route_sessions_to_test(monkeypatch, db_session)
    await _seed(db_session, 1, gem="g1", anth="a1", oai="o1", provider="openai")
    await _seed(db_session, 2, gem="g2", anth="a2", oai="o2", provider="anthropic")

    tok = _req_user_id.set(2)  # simulate user #2's request context
    try:
        assert await llm._resolve_gemini_key() == "g2"          # site 1
        assert await llm._resolve_anthropic_key() == "a2"        # site 2
        assert await embeddings._get_user_api_key() == "o2"      # site 3 (OpenAI)
        provider, prefs = await llm._active_settings()           # site 4 (provider/model)
        assert provider == "anthropic"
        assert prefs.get("anthropic") == "model-2"
    finally:
        _req_user_id.reset(tok)

    # Isolation: user #1's config is unaffected (explicit override, distinct cache slot).
    assert await llm._resolve_gemini_key(user_id=1) == "g1"
    assert (await llm._active_settings(user_id=1))[0] == "openai"


@pytest.mark.asyncio
async def test_background_force_platform_uses_env_key_and_never_the_user_resolver(monkeypatch):
    """Regression: background jobs (force_platform_key) resolve the ENV key and never touch the
    per-user resolver — byte-identical to before the multi-user fix."""
    from app.config import settings as s
    monkeypatch.setattr(s, "gemini_api_key", "ENV-GEMINI")

    async def _boom(*a, **k):
        raise AssertionError("per-user resolver must NOT run for force_platform_key")

    monkeypatch.setattr(llm, "_resolve_gemini_key", _boom)

    captured = {}
    import google.generativeai as genai

    class _Model:
        def __init__(self, *a, **k):
            pass

        async def generate_content_async(self, prompt):
            return type("R", (), {"text": "ok"})()

    monkeypatch.setattr(genai, "configure", lambda api_key=None: captured.__setitem__("key", api_key))
    monkeypatch.setattr(genai, "GenerativeModel", _Model)

    out = await llm._generate_gemini("hi", force_platform_key=True)
    assert out == "ok"
    assert captured["key"] == "ENV-GEMINI"  # env platform key, not any per-user key
