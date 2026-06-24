"""Standing follows (/follows) — behavior through the public HTTP interface.

These use the mock-session harness (no Postgres needed). Kind validation (400),
idempotency *branch*, and the GET/POST/DELETE shapes live here. Real-DB
idempotency + WHERE-clause filtering live in tests/integration/test_follows.py.
"""

from httpx import AsyncClient

from tests.conftest import FakeFollow, MockSession


class TestFollowValidation:
    """POST /follows — kind/value validation returns a clean 400 (not 422/500)."""

    async def test_invalid_kind_returns_400(self, client: AsyncClient):
        response = await client.post("/follows", json={"kind": "playlist", "value": "AI"})
        assert response.status_code == 400

    async def test_blank_value_returns_400(self, client: AsyncClient):
        response = await client.post("/follows", json={"kind": "topic", "value": "   "})
        assert response.status_code == 400

    async def test_missing_value_returns_422(self, client: AsyncClient):
        """Schema-level: a missing field is FastAPI's 422, before our 400 check."""
        response = await client.post("/follows", json={"kind": "topic"})
        assert response.status_code == 422


class TestFollowList:
    """GET /follows — the user's standing follows."""

    async def test_empty_list(self, client: AsyncClient, mock_session: MockSession):
        mock_session.follows = []
        response = await client.get("/follows")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_follows(self, client: AsyncClient, mock_session: MockSession):
        mock_session.follows = [
            FakeFollow(id=1, kind="topic", value="AI"),
            FakeFollow(id=2, kind="saved_search", value="opec cuts"),
            FakeFollow(id=3, kind="entity", value="Tesla"),
        ]
        response = await client.get("/follows")
        assert response.status_code == 200
        body = response.json()
        assert {f["value"] for f in body} == {"AI", "opec cuts", "Tesla"}
        assert {f["kind"] for f in body} == {"topic", "saved_search", "entity"}


class TestFollowCreate:
    """POST /follows — follow a topic/entity/saved_search."""

    async def test_create_returns_201_with_row(
        self, client: AsyncClient, mock_session: MockSession
    ):
        mock_session.follows = []  # nothing exists yet
        response = await client.post("/follows", json={"kind": "topic", "value": "Climate"})
        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "topic"
        assert body["value"] == "Climate"
        assert "id" in body and "created_at" in body
        assert mock_session.committed is True  # a row was written

    async def test_create_is_idempotent(
        self, client: AsyncClient, mock_session: MockSession
    ):
        """Re-following an identical (kind, value) returns the existing row, no insert."""
        mock_session.follows = [FakeFollow(id=7, kind="topic", value="Climate")]
        response = await client.post("/follows", json={"kind": "topic", "value": "Climate"})
        assert response.status_code == 201
        assert response.json()["id"] == 7
        assert mock_session.committed is False  # nothing new written

    async def test_create_trims_value(
        self, client: AsyncClient, mock_session: MockSession
    ):
        mock_session.follows = []
        response = await client.post("/follows", json={"kind": "entity", "value": "  Tesla  "})
        assert response.status_code == 201
        assert response.json()["value"] == "Tesla"


class TestFollowDelete:
    """DELETE /follows/{id} — unfollow (idempotent: always 204)."""

    async def test_delete_existing_removes_row(
        self, client: AsyncClient, mock_session: MockSession
    ):
        follow = FakeFollow(id=5, kind="topic", value="AI")
        mock_session.follows = [follow]
        response = await client.delete("/follows/5")
        assert response.status_code == 204
        assert follow in mock_session.deleted_objects

    async def test_delete_missing_is_noop_204(
        self, client: AsyncClient, mock_session: MockSession
    ):
        mock_session.follows = []
        response = await client.delete("/follows/999")
        assert response.status_code == 204
        assert mock_session.deleted_objects == []
