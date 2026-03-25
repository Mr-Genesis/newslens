"""
Tests for the encryption service — behavior through public interface.

Tests encrypt_value/decrypt_value without caring about Fernet internals.
"""

import pytest
from unittest.mock import patch


class TestEncryption:
    """Encryption service — encrypt and decrypt API keys."""

    def test_roundtrip_with_encryption_key(self):
        """Encrypting then decrypting returns the original value."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()

        with patch("app.services.encryption.settings") as mock_settings:
            mock_settings.encryption_key = key
            # Reset cached fernet
            import app.services.encryption as enc
            enc._fernet = None
            enc._warned = False

            from app.services.encryption import encrypt_value, decrypt_value

            original = "sk-test1234567890abcdef"
            encrypted = encrypt_value(original)
            decrypted = decrypt_value(encrypted)
            assert decrypted == original

    def test_encrypt_produces_different_output(self):
        """Encrypted value is not the same as the input (not plaintext)."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()

        with patch("app.services.encryption.settings") as mock_settings:
            mock_settings.encryption_key = key
            import app.services.encryption as enc
            enc._fernet = None
            enc._warned = False

            from app.services.encryption import encrypt_value

            original = "sk-test1234567890abcdef"
            encrypted = encrypt_value(original)
            assert encrypted != original

    def test_no_encryption_key_stores_plaintext(self):
        """Without ENCRYPTION_KEY, values are stored as plaintext."""
        with patch("app.services.encryption.settings") as mock_settings:
            mock_settings.encryption_key = ""
            import app.services.encryption as enc
            enc._fernet = None
            enc._warned = False

            from app.services.encryption import encrypt_value, decrypt_value

            original = "sk-plaintext-key"
            encrypted = encrypt_value(original)
            assert encrypted == original  # Plaintext fallback
            decrypted = decrypt_value(encrypted)
            assert decrypted == original
