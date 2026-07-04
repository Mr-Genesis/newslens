"""Unified LLM generation seam (E1 / E★).

Generation provider is switchable via ``settings.generation_provider`` ("openai"|"gemini").
Embeddings stay on OpenAI (see ``embeddings.py``) — do NOT route embeddings through here.
All generative features (summary, analysis, impact, strategic, trivia) should call ``generate()``.
"""
import json
import re
import time

import structlog

from app.config import settings

logger = structlog.get_logger()


class LLMUnavailable(Exception):
    """Raised when no usable LLM key/client is configured.

    Callers should catch this and return a typed ``unavailable`` state, never a 500.
    """


# ── Pure helper: robust JSON extraction from model output ──
def extract_json(text):
    """Best-effort parse of JSON from an LLM response.

    Handles already-parsed dict/list, ```json fenced blocks, and JSON embedded in prose.
    Raises ``ValueError`` if nothing parseable is found.
    """
    if isinstance(text, (dict, list)):
        return text
    if not text or not str(text).strip():
        raise ValueError("empty LLM output")
    s = str(text).strip()

    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()

    try:
        return json.loads(s)
    except Exception:
        pass

    # Fall back to the widest {...} or [...] span in the string.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = s.find(open_ch), s.rfind(close_ch)
        if 0 <= start < end:
            try:
                return json.loads(s[start:end + 1])
            except Exception:
                continue
    raise ValueError("could not parse JSON from model output")


# WS-6 (#116): all per-user resolution keys off the CURRENT request's user (current_user_id() — an
# async-task-local set by get_current_user), with an optional explicit user_id override, and PER-USER
# caches (were single global slots that leaked user #1's config to every caller). TTL 60s so a saved
# key/provider takes effect within a minute. Background jobs (force_platform_key) never hit these.
_GEM_TTL = 60


def _uid(user_id: int | None) -> int:
    from app.services.auth import current_user_id
    return user_id if user_id is not None else current_user_id()


def invalidate_user(user_id: int) -> None:
    """Drop a user's cached key/provider entries so a just-saved key/provider takes effect at once
    (belt-and-braces on top of the 60s TTL). Called by the settings write endpoints."""
    _gem_key_cache.pop(user_id, None)
    _anth_key_cache.pop(user_id, None)
    _active_cache.pop(user_id, None)


# ── Per-user Gemini key resolver ──
_gem_key_cache: dict[int, tuple[str | None, float]] = {}


async def _resolve_gemini_key(user_id: int | None = None) -> str | None:
    uid = _uid(user_id)
    now = time.time()
    hit = _gem_key_cache.get(uid)
    if hit is not None and (now - hit[1]) < _GEM_TTL:
        return hit[0]
    key = None
    try:
        from sqlalchemy import select
        from app.database import async_session
        from app.models import UserSetting
        from app.services.encryption import decrypt_value

        async with async_session() as s:
            row = (
                await s.execute(
                    select(UserSetting).where(
                        UserSetting.user_id == uid,
                        UserSetting.gemini_api_key_encrypted.isnot(None),
                        UserSetting.gemini_key_verified.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if row and row.gemini_api_key_encrypted:
                key = decrypt_value(row.gemini_api_key_encrypted)
    except Exception as e:  # noqa: BLE001
        logger.debug("gemini_key_lookup_failed", error=str(e))
    if not key:
        key = settings.gemini_api_key or None
    _gem_key_cache[uid] = (key, now)
    return key


# ── Per-user Anthropic key resolver ──
_anth_key_cache: dict[int, tuple[str | None, float]] = {}


async def _resolve_anthropic_key(user_id: int | None = None) -> str | None:
    uid = _uid(user_id)
    now = time.time()
    hit = _anth_key_cache.get(uid)
    if hit is not None and (now - hit[1]) < _GEM_TTL:
        return hit[0]
    key = None
    try:
        from sqlalchemy import select
        from app.database import async_session
        from app.models import UserSetting
        from app.services.encryption import decrypt_value

        async with async_session() as s:
            row = (
                await s.execute(
                    select(UserSetting).where(
                        UserSetting.user_id == uid,
                        UserSetting.anthropic_api_key_encrypted.isnot(None),
                        UserSetting.anthropic_key_verified.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if row and row.anthropic_api_key_encrypted:
                key = decrypt_value(row.anthropic_api_key_encrypted)
    except Exception as e:  # noqa: BLE001
        logger.debug("anthropic_key_lookup_failed", error=str(e))
    if not key:
        key = settings.anthropic_api_key or None
    _anth_key_cache[uid] = (key, now)
    return key


# ── Active provider + per-provider model overrides ──
_active_cache: dict[int, tuple[tuple[str, dict], float]] = {}


async def _active_settings(user_id: int | None = None) -> tuple[str, dict]:
    """(active_provider, model_prefs) for the CURRENT request's user (or an explicit user_id), cached
    60s. Falls back to the env generation_provider when no per-user choice is stored."""
    uid = _uid(user_id)
    now = time.time()
    hit = _active_cache.get(uid)
    if hit is not None and (now - hit[1]) < _GEM_TTL:
        return hit[0]
    provider = (settings.generation_provider or "openai").lower()
    prefs: dict = {}
    try:
        from sqlalchemy import select
        from app.database import async_session
        from app.models import UserSetting

        async with async_session() as s:
            row = (
                await s.execute(select(UserSetting).where(UserSetting.user_id == uid))
            ).scalar_one_or_none()
            if row:
                if row.active_provider:
                    provider = row.active_provider.lower()
                prefs = row.model_prefs or {}
    except Exception as e:  # noqa: BLE001
        logger.debug("active_provider_lookup_failed", error=str(e))
    _active_cache[uid] = ((provider, prefs), now)
    return _active_cache[uid][0]


def _model_default(provider: str) -> str:
    return {
        "openai": settings.summary_model,
        "gemini": settings.gemini_model,
        "anthropic": settings.anthropic_model,
    }.get(provider, settings.summary_model)


async def _generate_openai(prompt: str, *, system: str | None = None,
                           schema=None, model: str | None = None,
                           max_tokens: int | None = None,
                           force_platform_key: bool = False, user_id: int | None = None):
    # Module ref (not a bound import) so tests can patch embeddings._get_client_async.
    from app.services import embeddings
    # force_platform_key: background jobs (graph extraction) bill the platform/env key, never the
    # per-user key that _get_client_async resolves.
    client = (
        embeddings._get_client_platform()
        if force_platform_key
        else await embeddings._get_client_async(user_id)
    )
    if client is None:
        raise LLMUnavailable("no OpenAI key configured")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    kwargs = {
        "model": model or settings.summary_model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens or 800,
    }
    if schema is not None:
        kwargs["response_format"] = {"type": "json_object"}
    resp = await client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content
    return extract_json(text) if schema is not None else text.strip()


async def _generate_gemini(prompt: str, *, system: str | None = None,
                           schema=None, model: str | None = None,
                           max_tokens: int | None = None,
                           force_platform_key: bool = False, user_id: int | None = None):
    key = settings.gemini_api_key if force_platform_key else await _resolve_gemini_key(user_id)
    if not key:
        raise LLMUnavailable("no Gemini key configured")
    import google.generativeai as genai  # lazy import — only needed on the gemini path
    genai.configure(api_key=key)
    gen_config = {"temperature": 0.3}
    if max_tokens:
        gen_config["max_output_tokens"] = max_tokens
    if schema is not None:
        gen_config["response_mime_type"] = "application/json"
    gmodel = genai.GenerativeModel(
        model or settings.gemini_model,
        system_instruction=system,
        generation_config=gen_config,
    )
    resp = await gmodel.generate_content_async(prompt)
    return extract_json(resp.text) if schema is not None else resp.text.strip()


async def _generate_anthropic(prompt: str, *, system: str | None = None,
                              schema=None, model: str | None = None,
                              max_tokens: int | None = None,
                              force_platform_key: bool = False, user_id: int | None = None):
    key = settings.anthropic_api_key if force_platform_key else await _resolve_anthropic_key(user_id)
    if not key:
        raise LLMUnavailable("no Anthropic key configured")
    import anthropic  # lazy — only on the real anthropic path

    client = anthropic.AsyncAnthropic(api_key=key)
    messages = [{"role": "user", "content": prompt}]
    if schema is not None:
        # Prefill the assistant turn with "{" → forces pure-JSON output (Anthropic has no
        # response_format); we parse "{" + the returned text. Deterministic, no prose sandwich.
        messages.append({"role": "assistant", "content": "{"})
    kwargs = {
        "model": model or settings.anthropic_model,
        "max_tokens": max_tokens or 800,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system  # top-level, not a message role
    resp = await client.messages.create(**kwargs)
    text = "".join(
        getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
    )
    if schema is not None:
        return extract_json("{" + text)
    return text.strip()


async def generate(prompt: str, *, system: str | None = None,
                   schema=None, model: str | None = None,
                   max_tokens: int | None = None,
                   force_platform_key: bool = False, user_id: int | None = None):
    """Generate text (or parsed JSON when ``schema`` is given) via the chosen provider+model.

    Provider/model/key resolve for the CURRENT request's user (current_user_id(), an async-task-local
    set by get_current_user) unless an explicit ``user_id`` is passed. Provider = per-user
    active_provider (else env generation_provider). Model = explicit arg → per-user model_prefs[provider]
    → provider config default. ``force_platform_key`` routes to the platform/env key (background jobs),
    never a per-user key. Raises ``LLMUnavailable`` when no key.
    """
    provider, prefs = await _active_settings(user_id)
    resolved_model = model or prefs.get(provider) or _model_default(provider)
    if provider == "gemini":
        return await _generate_gemini(
            prompt, system=system, schema=schema, model=resolved_model, max_tokens=max_tokens,
            force_platform_key=force_platform_key, user_id=user_id,
        )
    if provider == "anthropic":
        return await _generate_anthropic(
            prompt, system=system, schema=schema, model=resolved_model, max_tokens=max_tokens,
            force_platform_key=force_platform_key, user_id=user_id,
        )
    return await _generate_openai(
        prompt, system=system, schema=schema, model=resolved_model, max_tokens=max_tokens,
        force_platform_key=force_platform_key, user_id=user_id,
    )
