from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field, field_validator

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
    coherence: Optional[float] = None  # real cluster coherence; None when unknown
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
    # None on the article-fallback path when the article has no cluster yet. It must NEVER carry an
    # article id: cluster and article ids are separate sequences, so a masqueraded id points the
    # deep-dive/lenses at a nonexistent or WRONG cluster as the sequences race past each other.
    cluster_id: int | None
    category: str
    source_count: int
    coherence: float
    is_read: bool = False
    # E6: best-effort WIIFM headline from already-cached impact_json (no new LLM calls)
    impact_headline: str | None = None


class BriefingResponse(BaseModel):
    stories: list[BriefingStory]
    generated_at: datetime
    explore_ratio: float = 0.3


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


# --- Settings ---
class UserSettingsOut(BaseModel):
    has_openai_key: bool
    openai_key_verified: bool = False
    openai_key_last4: str | None = None
    openai_key_verified_at: datetime | None = None
    # E1: mirror the OpenAI key trio for Gemini
    has_gemini_key: bool = False
    gemini_key_verified: bool = False
    gemini_key_last4: str | None = None
    gemini_key_verified_at: datetime | None = None
    # Wave E (BYOM): Anthropic key trio + the owner's active provider + per-provider model overrides
    has_anthropic_key: bool = False
    anthropic_key_verified: bool = False
    anthropic_key_last4: str | None = None
    anthropic_key_verified_at: datetime | None = None
    active_provider: str | None = None
    model_prefs: dict = Field(default_factory=dict)


class UserSettingsUpdate(BaseModel):
    openai_api_key: str | None = None  # raw key to save, or None to remove
    active_provider: str | None = None  # openai | anthropic | gemini
    model_prefs: dict | None = None     # {provider: model_id} overrides (merged server-side)


class KeyTestResult(BaseModel):
    success: bool
    error: str | None = None
    models_available: int = 0


# --- Profile (E3 + Wave A persona) ---
class WatchlistItem(BaseModel):
    type: str  # "ticker" | "entity" | "region" | "topic"
    value: str


class ProfileOut(BaseModel):
    profession: str | None = None
    locale: str = "IN"
    interests: list[str] = []
    watchlist: list[WatchlistItem] = []
    depth_pref: str = "standard"  # brief|standard|expert
    region: str | None = None


class ProfileUpdate(BaseModel):
    profession: str | None = None
    locale: str | None = None
    interests: list[str] | None = None  # topic names; replaces the user's preferences
    watchlist: list[WatchlistItem] | None = None
    depth_pref: str | None = None
    region: str | None = None


# --- Gemini key (E1) ---
class GeminiKeyUpdate(BaseModel):
    gemini_api_key: str | None = None  # raw key to save, or None to remove


class AnthropicKeyUpdate(BaseModel):
    anthropic_api_key: str | None = None  # raw key to save, or None to remove


# --- Saved ---
class SavedArticleOut(BaseModel):
    article_id: int
    title: str
    source_name: str
    snippet: str | None
    url: str
    cluster_id: int | None
    saved_at: datetime

    model_config = {"from_attributes": True}


class SavedListResponse(BaseModel):
    articles: list[SavedArticleOut]
    count: int


# --- Stats ---
class StatsResponse(BaseModel):
    articles_read: int
    stories_saved: int
    topics_explored: int


# --- Impact engine v2 (Wave A) ---
# Pydantic IS the contract (provider structured-output is best-effort; see lenses.impact).
# `not_advice` is stamped server-side, never model-generated.
class Horizon(str, Enum):
    now = "now"
    weeks = "weeks"
    quarter = "quarter"
    year_plus = "year_plus"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Evidence(BaseModel):
    claim: str
    source: str  # outlet name; must match a provided source (groundedness lint)


class Dimension(BaseModel):
    applicable: bool = False
    relevance: str = ""
    mechanism: str = ""
    watch_items: list[str] = Field(default_factory=list)
    horizon: Horizon = Horizon.year_plus
    confidence: Confidence = Confidence.low
    confidence_rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class FinancialDimension(Dimension):
    not_advice: bool = True  # stamped server-side after validation


class PersonalRelevance(BaseModel):
    score: Annotated[int, Field(ge=0, le=100)]  # range enforced here, not by the provider
    one_liner: str = ""


class Dimensions(BaseModel):
    professional: Dimension = Field(default_factory=Dimension)
    financial: FinancialDimension = Field(default_factory=FinancialDimension)
    civic: Dimension = Field(default_factory=Dimension)


class StoryImpact(BaseModel):
    cluster_id: str = ""
    headline: str = ""
    personal_relevance: PersonalRelevance       # required → missing raises
    dimensions: Dimensions                      # required → missing raises
    caveats: str = ""

    def relevance_band(self) -> str:
        s = self.personal_relevance.score
        return "high" if s >= 70 else ("notable" if s >= 40 else "low")


# --- Ask this story (Wave B1) ---
class AskRequest(BaseModel):
    question: str


class AskCitation(BaseModel):
    claim: str = ""
    source: str = ""  # outlet; must match a cluster source (groundedness)


class AskAnswer(BaseModel):
    answer: str = ""
    citations: list[AskCitation] = Field(default_factory=list)
    refused: bool = False


# --- Follows + digest (Wave C) ---
class FollowCreate(BaseModel):
    kind: str  # topic | entity | saved_search
    value: str
    entity_id: int | None = None  # G2: the tapped chip's entity id (kind=entity) — trustworthy link


class FollowOut(BaseModel):
    id: int
    kind: str
    value: str

    model_config = {"from_attributes": True}


class DigestItem(BaseModel):
    cluster_id: int
    title: str
    headline: str | None = None


class DigestResponse(BaseModel):
    count: int
    since: str
    items: list[DigestItem]


# --- G1 entity extraction (Wave D Phase 3) ---
_ENTITY_KINDS = {"person", "org", "place", "other"}


class ExtractedEntity(BaseModel):
    canonical_name: str
    kind: str = "other"
    salience: float = 0.0
    aliases: list[str] = Field(default_factory=list)

    @field_validator("canonical_name")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("empty canonical_name")
        return v.strip()

    @field_validator("kind", mode="before")
    @classmethod
    def _norm_kind(cls, v) -> str:
        s = str(v or "").strip().lower()
        return s if s in _ENTITY_KINDS else "other"

    @field_validator("salience", mode="before")
    @classmethod
    def _clamp_salience(cls, v) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))


class EntityExtraction(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
