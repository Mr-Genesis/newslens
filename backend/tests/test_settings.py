"""
Tests for Settings API endpoints — behavior through HTTP interface.

Tests GET/PUT /settings and POST /settings/test-key.
Uses mock session injection, no PostgreSQL required.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
from app.models import UserSetting


class FakeUserSetting:
    """Mimics UserSetting ORM model for testing."""

    def __init__(
        self,
        id=1,
        user_id=1,
        openai_api_key_encrypted=None,
        openai_key_verified=False,
        openai_key_verified_at=None,
    ):
        self.id = id
        self.user_id = user_id
        self.openai_api_key_encrypted = openai_api_key_encrypted
        self.openai_key_verified = openai_key_verified
        self.openai_key_verified_at = openai_key_verified_at
        self.updated_at = datetime.now(timezone.utc)


class SettingsMockSession:
    """Mock session that handles UserSetting queries."""

    def __init__(self):
        self.setting: FakeUserSetting | None = None
        self.added_objects: list = []
        self.committed = False

    async def execute(self, stmt, *args, **kwargs):
        """Return the stored setting for any select query."""

        class Result:
            def __init__(self, scalar):
                self._scalar = scalar

            def scalar_one_or_none(self):
                return self._scalar

            def scalars(self):
                return self

            def all(self):
                return [self._scalar] if self._scalar else []

        return Result(self.setting)

    def add(self, obj):
        self.added_objects.append(obj)
        # Simulate: the added object becomes the stored setting
        if isinstance(obj, UserSetting):
            self.setting = obj
            obj.id = 1
            obj.updated_at = datetime.now(timezone.utc)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        pass

    async def close(self):
        pass


@pytest.fixture
def settings_session():
    return SettingsMockSession()


@pytest.fixture
async def settings_client(settings_session):
    async def override_get_db():
        yield settings_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ─── GET /settings ───


class TestGetSettings:
    """GET /settings — retrieve current settings (masked)."""

    async def test_no_key_returns_has_openai_key_false(
        self, settings_client: AsyncClient, settings_session: SettingsMockSession
    ):
        """When no setting exists, returns has_openai_key=false."""
        settings_session.setting = None

        response = await settings_client.get("/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["has_openai_key"] is False
        assert data["openai_key_last4"] is None

    async def test_with_key_returns_masked(
        self, settings_client: AsyncClient, settings_session: SettingsMockSession
    ):
        """When a key is saved, returns has_openai_key=true with last 4 chars."""
        settings_session.setting = FakeUserSetting(
            openai_api_key_encrypted="sk-test1234567890",  # plaintext fallback
            openai_key_verified=True,
            openai_key_verified_at=datetime.now(timezone.utc),
        )

        with patch("app.services.encryption.decrypt_value", return_value="sk-test1234567890"):
            response = await settings_client.get("/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["has_openai_key"] is True
        assert data["openai_key_last4"] == "7890"
        assert data["openai_key_verified"] is True

    async def test_empty_encrypted_key_returns_no_key(
        self, settings_client: AsyncClient, settings_session: SettingsMockSession
    ):
        """Setting with null encrypted key returns has_openai_key=false."""
        settings_session.setting = FakeUserSetting(
            openai_api_key_encrypted=None,
        )

        response = await settings_client.get("/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["has_openai_key"] is False


# ─── PUT /settings ───


class TestUpdateSettings:
    """PUT /settings — save or remove API key."""

    async def test_save_key(
        self, settings_client: AsyncClient, settings_session: SettingsMockSession
    ):
        """Saving a key returns has_openai_key=true with masked last4."""
        settings_session.setting = None

        with patch("app.services.encryption.encrypt_value", return_value="encrypted_value"):
            with patch("app.services.encryption.decrypt_value", return_value="sk-newkey1234"):
                response = await settings_client.put(
                    "/settings",
                    json={"openai_api_key": "sk-newkey1234"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["has_openai_key"] is True
        assert data["openai_key_last4"] == "1234"

    async def test_remove_key(
        self, settings_client: AsyncClient, settings_session: SettingsMockSession
    ):
        """Setting key to null removes it."""
        settings_session.setting = FakeUserSetting(
            openai_api_key_encrypted="some_encrypted_value",
        )

        response = await settings_client.put(
            "/settings",
            json={"openai_api_key": None},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_openai_key"] is False
        assert data["openai_key_last4"] is None


# ─── POST /settings/test-key ───


class TestTestKey:
    """POST /settings/test-key — validate saved API key."""

    async def test_no_key_returns_error(
        self, settings_client: AsyncClient, settings_session: SettingsMockSession
    ):
        """Testing with no saved key returns error."""
        settings_session.setting = None

        response = await settings_client.post("/settings/test-key")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "No API key saved"

    async def test_invalid_key_returns_error(
        self, settings_client: AsyncClient, settings_session: SettingsMockSession
    ):
        """Testing with an invalid key returns error."""
        settings_session.setting = FakeUserSetting(
            openai_api_key_encrypted="sk-invalid",
        )

        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(
            side_effect=Exception("Incorrect API key provided")
        )

        with patch("app.services.encryption.decrypt_value", return_value="sk-invalid"):
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                response = await settings_client.post("/settings/test-key")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid API key" in (data["error"] or "")

    async def test_valid_key_succeeds(
        self, settings_client: AsyncClient, settings_session: SettingsMockSession
    ):
        """Testing with a valid key returns success and model count."""
        settings_session.setting = FakeUserSetting(
            openai_api_key_encrypted="sk-valid",
        )

        mock_models = MagicMock()
        mock_models.data = [MagicMock(), MagicMock(), MagicMock()]  # 3 models

        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=mock_models)

        with patch("app.services.encryption.decrypt_value", return_value="sk-valid"):
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                response = await settings_client.post("/settings/test-key")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["models_available"] == 3
