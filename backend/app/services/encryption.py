"""Symmetric encryption for sensitive data (API keys) using Fernet.

If ENCRYPTION_KEY is not set, falls back to plaintext storage with a warning.
Generate a key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import structlog

from app.config import settings

logger = structlog.get_logger()

_fernet = None
_warned = False


def _get_fernet():
    global _fernet, _warned
    if _fernet is not None:
        return _fernet

    if not settings.encryption_key:
        if not _warned:
            logger.warning(
                "encryption_key_not_set",
                msg="API keys will be stored as plaintext. Set ENCRYPTION_KEY for production.",
            )
            _warned = True
        return None

    from cryptography.fernet import Fernet

    _fernet = Fernet(settings.encryption_key.encode())
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string → hex ciphertext.

    With no ENCRYPTION_KEY: raises if require_encryption is set (production safety),
    otherwise falls back to plaintext with a warning (dev/test).
    """
    f = _get_fernet()
    if f is None:
        if settings.require_encryption:
            raise RuntimeError(
                "ENCRYPTION_KEY is required (REQUIRE_ENCRYPTION=true) but not set — "
                "refusing to store a secret as plaintext."
            )
        return plaintext
    return f.encrypt(plaintext.encode()).hex()


def decrypt_value(stored: str) -> str:
    """Decrypt a stored value.

    With no ENCRYPTION_KEY configured: the value was stored as plaintext, so return
    it as-is. With a Fernet configured: decryption MUST succeed — on any failure we
    raise rather than leak the raw stored ciphertext back to the caller.
    """
    f = _get_fernet()
    if f is None:
        return stored

    try:
        return f.decrypt(bytes.fromhex(stored)).decode()
    except Exception as e:
        # A Fernet is configured but the stored value could not be decrypted.
        # Never return the raw ciphertext — fail loudly instead.
        logger.error("decrypt_failed", error=str(e))
        raise ValueError("Failed to decrypt stored value") from e
