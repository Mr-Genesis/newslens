"""
Test fixtures for NewsLens API tests.

Tests use dependency injection to override the database session with
mock data, avoiding the need for a running PostgreSQL instance.
The health endpoint is tested separately since it bypasses dependency injection.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.models import (
    Article,
    ClusterArticle,
    EmbeddingStatus,
    FeedbackType,
    Source,
    SourceType,
    StoryCluster,
    Topic,
    UserFeedback,
)


# --- Data factory helpers using simple dataclass-like objects ---

class FakeSource:
    """Mimics Source ORM model for testing without SQLAlchemy instrumentation."""

    def __init__(self, id=1, name="Reuters", url="https://reuters.com",
                 source_type=SourceType.wire, is_paywalled=False):
        self.id = id
        self.name = name
        self.url = url
        self.rss_url = f"{url}/rss"
        self.source_type = source_type
        self.is_paywalled = is_paywalled
        self.created_at = datetime.now(timezone.utc)
        self.articles = []


class FakeArticle:
    """Mimics Article ORM model for testing."""

    def __init__(self, id=1, title="Test Article", snippet="Test snippet...",
                 url="https://reuters.com/test", source=None, source_id=1,
                 embedding_status=EmbeddingStatus.pending, published_at=None):
        self.id = id
        self.title = title
        self.snippet = snippet
        self.url = url
        self.source_id = source_id
        self.source = source or FakeSource(id=source_id)
        self.embedding_status = embedding_status
        self.published_at = published_at or datetime.now(timezone.utc)
        self.fetched_at = datetime.now(timezone.utc)
        self.embedding = None
        self.topics = []
        self.clusters = []
        self.feedback = []


class FakeCluster:
    """Mimics StoryCluster ORM model for testing."""

    def __init__(self, id=1, title="EU AI Regulation",
                 summary="The EU passed sweeping AI regulation...",
                 cluster_articles=None):
        self.id = id
        self.title = title
        self.summary = summary
        self.created_at = datetime.now(timezone.utc)
        self.articles = cluster_articles or []


class FakeClusterArticle:
    """Mimics ClusterArticle ORM model for testing."""

    def __init__(self, id=1, cluster_id=1, article=None):
        self.id = id
        self.cluster_id = cluster_id
        self.article = article or FakeArticle()
        self.article_id = self.article.id


class FakeTopic:
    """Mimics Topic ORM model for testing."""

    def __init__(self, id=1, name="Technology"):
        self.id = id
        self.name = name
        self.parent_topic_id = None
        self.embedding = None
        self.created_at = datetime.now(timezone.utc)
        self.articles = []
        self.children = []


def make_source(**kwargs) -> FakeSource:
    return FakeSource(**kwargs)


def make_article(**kwargs) -> FakeArticle:
    return FakeArticle(**kwargs)


def make_cluster(**kwargs) -> FakeCluster:
    return FakeCluster(**kwargs)


def make_cluster_article(**kwargs) -> FakeClusterArticle:
    return FakeClusterArticle(**kwargs)


def make_topic(**kwargs) -> FakeTopic:
    return FakeTopic(**kwargs)


# --- Mock session that simulates SQLAlchemy query results ---

class MockExecuteResult:
    """Simulates SQLAlchemy execute result."""

    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar


class MockSession:
    """
    Mock AsyncSession that returns preconfigured data.

    Set `.feed_articles`, `.feed_total`, `.cluster`, `.topics`
    to control what the mock returns for each endpoint.
    """

    def __init__(self):
        self.feed_articles: list[Article] = []
        self.feed_total: int = 0
        self.cluster: StoryCluster | None = None
        self.topics: list[Topic] = []
        self.added_objects: list = []
        self.committed = False
        self._last_feedback_id = 100

    async def execute(self, stmt, *args, **kwargs):
        stmt_str = str(stmt)

        # Detect which query is being run by inspecting the compiled SQL
        if hasattr(stmt, 'column_descriptions'):
            # Check what the select is targeting
            if hasattr(stmt, 'column_descriptions'):
                for desc in stmt.column_descriptions:
                    entity = desc.get('entity') or desc.get('type')
                    if entity is StoryCluster:
                        return MockExecuteResult(scalar=self.cluster)
                    if entity is Topic:
                        return MockExecuteResult(rows=self.topics)
                    if entity is Article:
                        return MockExecuteResult(rows=self.feed_articles)

        # Count query (returns int)
        if 'count' in str(stmt).lower() or 'anon_1' in str(stmt).lower():
            return MockExecuteResult(scalar=self.feed_total)

        # Default: return articles for feed
        return MockExecuteResult(rows=self.feed_articles)

    def add(self, obj):
        self.added_objects.append(obj)

    async def commit(self):
        self.committed = True
        # Simulate auto-generating IDs for feedback
        for obj in self.added_objects:
            if isinstance(obj, UserFeedback) and not hasattr(obj, 'id') or getattr(obj, 'id', None) is None:
                obj.id = self._last_feedback_id
                self._last_feedback_id += 1
                obj.created_at = datetime.now(timezone.utc)

    async def refresh(self, obj):
        pass

    async def close(self):
        pass


@pytest.fixture
def mock_session():
    """Provide a MockSession for dependency injection."""
    return MockSession()


@pytest_asyncio.fixture
async def client(mock_session: MockSession):
    """Async HTTP client with mock database session."""

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# --- Pre-configured data fixtures ---

@pytest.fixture
def free_source():
    return make_source(id=1, name="Reuters", is_paywalled=False)


@pytest.fixture
def paywalled_source():
    return make_source(
        id=2, name="Wall Street Journal",
        url="https://wsj.com", is_paywalled=True,
    )


@pytest.fixture
def reuters_article(free_source):
    return make_article(
        id=1,
        title="EU passes AI act — Reuters",
        snippet="The European Parliament approved the AI Act...",
        url="https://reuters.com/eu-ai-act",
        source=free_source,
        source_id=free_source.id,
    )


@pytest.fixture
def wsj_article(paywalled_source):
    return make_article(
        id=2,
        title="AI Regulation: What It Means — WSJ",
        snippet="Tech companies scramble to assess impact...",
        url="https://wsj.com/ai-regulation",
        source=paywalled_source,
        source_id=paywalled_source.id,
    )


@pytest.fixture
def cluster_with_sources(reuters_article, wsj_article):
    ca_free = make_cluster_article(id=1, cluster_id=1, article=reuters_article)
    ca_paid = make_cluster_article(id=2, cluster_id=1, article=wsj_article)
    return make_cluster(
        id=1,
        title="EU AI Regulation",
        summary="The EU passed sweeping AI regulation...",
        cluster_articles=[ca_free, ca_paid],
    )
