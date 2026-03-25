"""
NewsLens API tests — behavior through the public HTTP interface.

Each test describes what the API DOES, not how it's implemented.
Tests use mock session injection — no PostgreSQL required.
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from tests.conftest import MockSession, make_article, make_source, make_topic


# ─── Health ───


class TestHealth:
    """GET /health — system health check."""

    async def test_health_ok_when_db_reachable(self, client: AsyncClient):
        """Health returns ok when database responds."""
        with patch("app.api.routes.async_session") as mock_session_maker:
            mock_ctx = AsyncMock()
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.execute = AsyncMock()

            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["db"] is True

    async def test_health_degraded_when_db_unreachable(self, client: AsyncClient):
        """Health returns degraded when database is down."""
        with patch("app.api.routes.async_session") as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert data["db"] is False


# ─── Feed ───


class TestFeed:
    """GET /feed — paginated article feed."""

    async def test_empty_feed(self, client: AsyncClient, mock_session: MockSession):
        """Feed with no articles returns empty list."""
        mock_session.feed_articles = []
        mock_session.feed_total = 0

        response = await client.get("/feed")
        assert response.status_code == 200
        data = response.json()
        assert data["articles"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["per_page"] == 20
        assert "explore_ratio" in data

    async def test_feed_returns_articles(self, client: AsyncClient, mock_session: MockSession):
        """Feed includes articles with source information."""
        source = make_source(id=1, name="Reuters", is_paywalled=False)
        article = make_article(
            id=1,
            title="AI Regulation in Europe",
            snippet="The EU has passed a landmark bill...",
            source=source,
            source_id=source.id,
        )
        mock_session.feed_articles = [article]
        mock_session.feed_total = 1

        response = await client.get("/feed")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["articles"]) == 1
        art = data["articles"][0]
        assert art["title"] == "AI Regulation in Europe"
        assert art["source"]["name"] == "Reuters"
        assert art["source"]["is_paywalled"] is False

    async def test_feed_pagination_params(self, client: AsyncClient, mock_session: MockSession):
        """Feed respects page and per_page parameters."""
        mock_session.feed_articles = []
        mock_session.feed_total = 0

        response = await client.get("/feed?page=2&per_page=5")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["per_page"] == 5

    async def test_feed_rejects_page_zero(self, client: AsyncClient):
        """Feed rejects page < 1."""
        response = await client.get("/feed?page=0")
        assert response.status_code == 422

    async def test_feed_rejects_oversized_per_page(self, client: AsyncClient):
        """Feed rejects per_page > 100."""
        response = await client.get("/feed?per_page=200")
        assert response.status_code == 422


# ─── Clusters / Deep Dive ───


class TestClusters:
    """GET /clusters/{id} — story cluster with multi-source view."""

    async def test_cluster_not_found(self, client: AsyncClient, mock_session: MockSession):
        """Non-existent cluster returns 404."""
        mock_session.cluster = None

        response = await client.get("/clusters/99999")
        assert response.status_code == 404

    async def test_cluster_returns_sources(
        self, client: AsyncClient, mock_session: MockSession, cluster_with_sources
    ):
        """Cluster returns title, summary, and source articles."""
        mock_session.cluster = cluster_with_sources

        response = await client.get(f"/clusters/{cluster_with_sources.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "EU AI Regulation"
        assert data["summary"] == "The EU passed sweeping AI regulation..."
        assert len(data["sources"]) == 2

    async def test_cluster_free_sources_first(
        self, client: AsyncClient, mock_session: MockSession, cluster_with_sources
    ):
        """Free sources appear before paywalled sources in the response."""
        mock_session.cluster = cluster_with_sources

        response = await client.get(f"/clusters/{cluster_with_sources.id}")
        data = response.json()
        sources = data["sources"]

        # First source should be free (Reuters)
        assert sources[0]["is_free"] is True
        assert sources[0]["article"]["source"]["name"] == "Reuters"

        # Second source should be paywalled (WSJ)
        assert sources[1]["is_free"] is False
        assert sources[1]["article"]["source"]["name"] == "Wall Street Journal"


# ─── Topics ───


class TestTopics:
    """GET /topics — topic list grouped by category."""

    async def test_empty_topics(self, client: AsyncClient, mock_session: MockSession):
        """Topics returns empty groups when no topics exist."""
        mock_session.topics = []

        response = await client.get("/topics")
        assert response.status_code == 200
        data = response.json()
        assert data["your_topics"] == []
        assert data["explore_topics"] == []
        assert data["trending_topics"] == []

    async def test_topics_in_your_topics(self, client: AsyncClient, mock_session: MockSession):
        """Existing topics appear in your_topics (MVP behavior)."""
        mock_session.topics = [make_topic(id=1, name="Technology")]

        response = await client.get("/topics")
        assert response.status_code == 200
        data = response.json()
        assert len(data["your_topics"]) == 1
        assert data["your_topics"][0]["name"] == "Technology"
        # MVP: explore and trending are always empty
        assert data["explore_topics"] == []
        assert data["trending_topics"] == []


# ─── Feedback ───


class TestFeedback:
    """POST /feedback — record user feedback on articles."""

    async def test_create_feedback(self, client: AsyncClient, mock_session: MockSession):
        """Creating feedback returns 201 with feedback data."""
        response = await client.post(
            "/feedback",
            json={"article_id": 1, "feedback_type": "interesting"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["article_id"] == 1
        assert data["feedback_type"] == "interesting"
        assert "id" in data
        assert "created_at" in data

    async def test_feedback_save_type(self, client: AsyncClient, mock_session: MockSession):
        """Feedback with 'save' type is accepted."""
        response = await client.post(
            "/feedback",
            json={"article_id": 1, "feedback_type": "save"},
        )
        assert response.status_code == 201
        assert response.json()["feedback_type"] == "save"

    async def test_feedback_invalid_type(self, client: AsyncClient):
        """Feedback with invalid type returns 422."""
        response = await client.post(
            "/feedback",
            json={"article_id": 1, "feedback_type": "invalid_type"},
        )
        assert response.status_code == 422

    async def test_feedback_missing_article_id(self, client: AsyncClient):
        """Feedback without article_id returns 422."""
        response = await client.post(
            "/feedback",
            json={"feedback_type": "interesting"},
        )
        assert response.status_code == 422

    async def test_feedback_missing_type(self, client: AsyncClient):
        """Feedback without feedback_type returns 422."""
        response = await client.post(
            "/feedback",
            json={"article_id": 1},
        )
        assert response.status_code == 422
