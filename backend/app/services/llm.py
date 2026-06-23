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


# ── Per-user Gemini key resolver (separate cache slot from the OpenAI one) ──
# NOTE: per-user DB key (user_settings.gemini_api_key_encrypted) lands with the E1
# migration; until then this resolves the env key. Kept as a seam so callers don't change.
_gem_key_cache: str | None = None
_gem_key_ts: float = 0.0
_GEM_TTL = 300


async def _resolve_gemini_key() -> str | None:
    global _gem_key_cache, _gem_key_ts
    now = time.time()
    if _gem_key_cache is not None and (now - _gem_key_ts) < _GEM_TTL:
        return _gem_key_cache
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
                        UserSetting.user_id == 1,
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
    _gem_key_cache, _gem_key_ts = key, now
    return key


async def _generate_openai(prompt: str, *, system: str | None = None,
                           schema=None, model: str | None = None,
                           max_tokens: int | None = None):
    # Module ref (not a bound import) so tests can patch embeddings._get_client_async.
    from app.services import embeddings
    client = await embeddings._get_client_async()
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
                           max_tokens: int | None = None):
    key = await _resolve_gemini_key()
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


async def generate(prompt: str, *, system: str | None = None,
                   schema=None, model: str | None = None,
                   max_tokens: int | None = None):
    """Generate text (or parsed JSON when ``schema`` is given) via the configured provider.

    Raises ``LLMUnavailable`` when no key is configured.
    """
    provider = (settings.generation_provider or "openai").lower()
    if provider == "gemini":
        return await _generate_gemini(
            prompt, system=system, schema=schema, model=model, max_tokens=max_tokens
        )
    return await _generate_openai(
        prompt, system=system, schema=schema, model=model, max_tokens=max_tokens
    )
