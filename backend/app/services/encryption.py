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
    """Encrypt a string. Returns hex-encoded ciphertext, or plaintext if no key configured."""
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).hex()


def decrypt_value(stored: str) -> str:
    """Decrypt a stored value. Handles both encrypted (hex) and plaintext fallback."""
    f = _get_fernet()
    if f is None:
        return stored

    try:
        return f.decrypt(bytes.fromhex(stored)).decode()
    except Exception:
        # Might be plaintext from before encryption was enabled
        logger.warning("decrypt_fallback_plaintext")
        return stored
