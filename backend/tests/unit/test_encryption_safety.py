"""E0 safety: encryption fail-fast vs dev fallback (pure unit, native)."""
import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.services import encryption


@pytest.fixture(autouse=True)
def reset_fernet():
    encryption._fernet = None
    encryption._warned = False
    yield
    encryption._fernet = None
    encryption._warned = False


def test_fallback_to_plaintext_when_not_required(monkeypatch):
    monkeypatch.setattr(settings, "encryption_key", "")
    monkeypatch.setattr(settings, "require_encryption", False)
    assert encryption.encrypt_value("sk-secret") == "sk-secret"


def test_failfast_when_required_and_no_key(monkeypatch):
    monkeypatch.setattr(settings, "encryption_key", "")
    monkeypatch.setattr(settings, "require_encryption", True)
    with pytest.raises(RuntimeError):
        encryption.encrypt_value("sk-secret")


def test_roundtrip_with_key(monkeypatch):
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "require_encryption", True)
    enc = encryption.encrypt_value("sk-secret")
    assert enc != "sk-secret"
    assert encryption.decrypt_value(enc) == "sk-secret"


def test_decrypt_failure_does_not_leak_ciphertext(monkeypatch):
    # With a real Fernet configured, a corrupted/invalid token must RAISE — never
    # return the raw stored value back to the caller (would leak ciphertext).
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "require_encryption", True)

    corrupted = "deadbeef" * 8  # valid hex, but not a real Fernet token
    with pytest.raises(ValueError) as exc:
        encryption.decrypt_value(corrupted)

    # The raised error must not echo the ciphertext back.
    assert corrupted not in str(exc.value)

    # Also covers a non-hex token (bytes.fromhex itself fails) — still raises, no leak.
    with pytest.raises(ValueError):
        encryption.decrypt_value("not-hex-zzzz")
