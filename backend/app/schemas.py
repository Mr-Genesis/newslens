from datetime import datetime

from pydantic import BaseModel

from app.models import EmbeddingStatus, FeedbackType, SourceType


# --- Source ---
class SourceOut(BaseModel):
    id: int
    name: str
    url: str
    source_type: SourceType
    is_paywalled: bool

    model_config = {"from_attributes": True}


# --- Article ---
class ArticleOut(BaseModel):
    id: int
    title: str
    snippet: str | None
    url: str
    source: SourceOut
    published_at: datetime | None
    embedding_status: EmbeddingStatus
    source_count: int = 1  # how many sources cover this story
    cluster_id: int | None = None
    has_ai_summary: bool = False
    feedback: list[FeedbackType] = []  # user's existing feedback on this article

    model_config = {"from_attributes": True}


# --- Feed ---
class FeedResponse(BaseModel):
    articles: list[ArticleOut]
    total: int
    page: int
    per_page: int
    explore_ratio: float


# --- Cluster / Deep Dive ---
class ClusterSourceCard(BaseModel):
    article: ArticleOut
    is_free: bool

    model_config = {"from_attributes": True}


class ClusterDetailOut(BaseModel):
    id: int
    title: str
    summary: str | None
    created_at: datetime
    sources: list[ClusterSourceCard]  # sorted: free first, then paywalled

    model_config = {"from_attributes": True}


# --- Topic ---
class TopicOut(BaseModel):
    id: int
    name: str
    article_count: int = 0
    is_explore: bool = False  # true if this is a breadth-expansion topic for the user

    model_config = {"from_attributes": True}


class TopicListResponse(BaseModel):
    your_topics: list[TopicOut]
    explore_topics: list[TopicOut]
    trending_topics: list[TopicOut]


# --- Feedback ---
class FeedbackCreate(BaseModel):
    article_id: int
    feedback_type: FeedbackType


class FeedbackOut(BaseModel):
    id: int
    article_id: int
    feedback_type: FeedbackType
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Health ---
class HealthResponse(BaseModel):
    status: str  # "ok" or "degraded"
    db: bool


# --- Admin ---
class SourceHealthOut(BaseModel):
    id: int
    name: str
    url: str
    last_fetch_at: datetime | None
    error_rate: float  # 0.0-1.0
    article_count: int
    is_healthy: bool


class BreadthMetricsOut(BaseModel):
    current_explore_ratio: float
    explore_engagement_rate: float  # % of explore cards with positive feedback
    exploit_engagement_rate: float
    topic_diversity_score: float  # unique topics / total articles in recent window
    explore_ratio_history: list[dict]  # [{timestamp, ratio}]


# --- Briefing ---
class BriefingStory(BaseModel):
    title: str
    summary: str
    cluster_id: int
    category: str
    source_count: int
    coherence: float
    is_read: bool = False


class BriefingResponse(BaseModel):
    stories: list[BriefingStory]
    generated_at: datetime


# --- Discover ---
class DiscoverCardOut(BaseModel):
    id: int
    article_id: int
    title: str
    tension_line: str
    facts: list[str]
    sources: list[str]
    topic_id: int
    topic_name: str
    coherence: float


class SwipeRequest(BaseModel):
    article_id: int
    direction: str  # "right" | "left" | "up"
