import enum
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DDL,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base


class EmbeddingStatus(str, enum.Enum):
    pending = "pending"
    complete = "complete"
    failed = "failed"


class FeedbackType(str, enum.Enum):
    interesting = "interesting"
    less = "less"
    save = "save"
    share = "share"
    read = "read"


class SourceType(str, enum.Enum):
    newspaper = "newspaper"
    blog = "blog"
    channel = "channel"
    wire = "wire"
    other = "other"
    # Phase 1 source expansion — persona-gated tiers.
    research = "research"  # journals / preprints (arXiv, NEJM, medRxiv…)
    expert = "expert"      # individual expert blogs, credibility-scored (Substack…)
    # Official-sources plan (docs/official-sources-plan.md) — both gated; admission differs:
    official = "official"  # regulator/central-bank/ministry/exchange notices — audience-gated
    filing = "filing"      # per-company disclosures (EDGAR, NSE/BSE) — watchlist/follow-only


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # E3: profession-agnostic personalization (free-text profession + locale)
    profession: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locale: Mapped[str] = mapped_column(String(16), default="IN")
    # Wave A: richer persona for the impact engine. interests stay in user_preferences
    # (topic rows); these add the watchlist + presentation prefs. persona_version bumps
    # on any profile edit to lazily invalidate cached impacts.
    watchlist: Mapped[list | None] = mapped_column(
        JSONB, default=list
    )  # [{"type":"ticker","value":"NVDA"},{"type":"region","value":"US-CA"}]
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    depth_pref: Mapped[str] = mapped_column(
        String(16), default="standard"
    )  # brief|standard|expert
    persona_version: Mapped[int] = mapped_column(Integer, default=1)
    # Wave C: "while you were away" gating.
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Wave D Phase A: Firebase identity (multi-user). UNIQUE on non-NULL uids — Postgres allows
    # many NULLs in a unique index, so the default user + any legacy rows stay NULL without conflict.
    firebase_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("uq_users_firebase_uid", "firebase_uid", unique=True),
    )

    feedback: Mapped[list["UserFeedback"]] = relationship(back_populates="user")
    preferences: Mapped[list["UserPreference"]] = relationship(back_populates="user")
    settings: Mapped["UserSetting | None"] = relationship(
        back_populates="user", uselist=False
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    rss_url: Mapped[str | None] = mapped_column(String(2048))
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType), default=SourceType.other
    )
    is_paywalled: Mapped[bool] = mapped_column(Boolean, default=False)
    # E2: region ("global" | "in") + free-form category for India/topic sourcing
    region: Mapped[str | None] = mapped_column(String(16), default="global")
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ── Phase 1 source expansion (all nullable/additive) ──
    # Named author for the expert tier; the credibility score (0-100) is the editorial
    # admission control — below the briefing/feed floors a source is gated out. credibility_meta
    # holds {affiliation, credentials, rationale, reviewed_by: seed|llm-proposed|admin, ...}; a
    # reviewed_by="admin" row is locked against the sources.json re-upsert.
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credibility_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    credibility_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Persona tags (["medicine","ai"…]); NULL = general audience (shown to everyone).
    audience: Mapped[list | None] = mapped_column(ARRAY(String), nullable=True)
    is_preprint: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Newest-first cap per fetch (arXiv emits ~600 papers/day). NULL = no cap.
    per_fetch_cap: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    articles: Mapped[list["Article"]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)  # ≤300 chars, for cards
    # Wave D1: full extracted article body (for deep retrieval; snippet stays for cards).
    extracted_text: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        Enum(EmbeddingStatus), default=EmbeddingStatus.pending
    )
    embedding = mapped_column(Vector(settings.embedding_dimensions), nullable=True)

    __table_args__ = (
        UniqueConstraint("url", "source_id", name="uq_article_url_source"),
        # WS-1 (#111): plain b-tree indexes for the date predicates the wave adds (rails' 72h
        # recency window on published_at, the as_of cursor on fetched_at). Plain — not
        # DESC-NULLS-LAST expression indexes — to keep autogenerate parity (the HNSW index is
        # already the one tolerated exception).
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_fetched_at", "fetched_at"),
    )

    source: Mapped["Source"] = relationship(back_populates="articles")
    topics: Mapped[list["ArticleTopic"]] = relationship(back_populates="article")
    clusters: Mapped[list["ClusterArticle"]] = relationship(back_populates="article")
    feedback: Mapped[list["UserFeedback"]] = relationship(back_populates="article")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    parent_topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    embedding = mapped_column(Vector(settings.embedding_dimensions), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    articles: Mapped[list["ArticleTopic"]] = relationship(back_populates="topic")
    children: Mapped[list["Topic"]] = relationship()


class ArticleTopic(Base):
    __tablename__ = "article_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("article_id", "topic_id", name="uq_article_topic"),
    )

    article: Mapped["Article"] = relationship(back_populates="topics")
    topic: Mapped["Topic"] = relationship(back_populates="articles")


class StoryCluster(Base):
    __tablename__ = "story_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    coherence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # E5/E6/E7/E8: cached LLM lens outputs (keyed by profession-hash inside the JSON
    # where personalized). source_hash invalidates caches when the cluster's article
    # set changes.
    analysis_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    impact_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    strategic_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trivia_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Wave B: umbrella cache for newer lenses (frameworks, consensus) keyed by subkey.
    extra_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    articles: Mapped[list["ClusterArticle"]] = relationship(back_populates="cluster")


class ClusterArticle(Base):
    __tablename__ = "cluster_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("story_clusters.id"), nullable=False
    )
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("cluster_id", "article_id", name="uq_cluster_article"),
    )

    cluster: Mapped["StoryCluster"] = relationship(back_populates="articles")
    article: Mapped["Article"] = relationship(back_populates="clusters")


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType), nullable=False
    )
    # WS-1 (#111): dwell + click attribution. duration_ms rides the auto-`read` row (upserted with
    # GREATEST on story close); surface names WHERE the tap happened (briefing|feed|rail|discover|
    # search) — the CTR numerator that pairs with impressions' denominator.
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="feedback")
    article: Mapped["Article"] = relationship(back_populates="feedback")


class Impression(Base):
    """WS-1 (#111): what a user SAW per surface — the rec engine's perishable negative-space signal.

    Deduped per (user, story, surface, day) via an EXPRESSION unique index: cluster_id/article_id are
    nullable (briefing fallback cards are clusterless), and plain NULLs never conflict in a unique
    index — so the key COALESCEs both to 0. `day` is a stored column, NOT date(created_at): that cast
    isn't IMMUTABLE over timestamptz, so an expression index on it can't exist. RLS-scoped."""

    __tablename__ = "impressions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("story_clusters.id", ondelete="CASCADE"), nullable=True
    )
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=True
    )
    surface: Mapped[str] = mapped_column(String(16), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "cluster_id IS NOT NULL OR article_id IS NOT NULL", name="ck_impression_target"
        ),
        Index(
            "uq_impression_day",
            text("user_id"),
            text("COALESCE(cluster_id, 0)"),
            text("COALESCE(article_id, 0)"),
            text("surface"),
            text("day"),
            unique=True,
        ),
        Index("ix_impressions_user_created", "user_id", "created_at"),
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    breadth_score: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_user_topic_pref"),
    )

    user: Mapped["User"] = relationship(back_populates="preferences")
    topic: Mapped["Topic"] = relationship()


class UserSetting(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, unique=True
    )
    openai_api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    openai_key_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    openai_key_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # E1: per-user Gemini key (mirrors the OpenAI trio)
    gemini_api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    gemini_key_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    gemini_key_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Wave E (BYOM): per-user Anthropic key (mirrors the trio) + active provider + Anthropic model
    anthropic_api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    anthropic_key_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    anthropic_key_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    active_provider: Mapped[str | None] = mapped_column(String(16))  # openai|anthropic|gemini; NULL→env
    model_prefs: Mapped[dict | None] = mapped_column(JSONB, default=dict)  # {provider: model_id} overrides
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="settings")


class Follow(Base):
    """Wave C: a standing follow — topic / entity / saved-search → feed rail + alerts."""

    __tablename__ = "follows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # topic|entity|saved_search
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    # G2: the resolved entity behind an entity-follow (from the tapped chip). Nullable keeps uq_follow
    # live with no orphan window; the string-path follow leaves it NULL.
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"))
    # WS-2 (#112) badges: when the user last opened THIS rail. new_count = rail stories newer than it.
    # Per-follow (NOT the global User.last_seen_at, which /digest resets on every read). NULL = never
    # viewed → every current story counts as new.
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "kind", "value", name="uq_follow"),
        Index("ix_follows_entity", "entity_id"),
    )


class ClusterEdge(Base):
    """Wave D2: directed temporal/topical edges between existing clusters → "how we got here"."""

    __tablename__ = "cluster_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("story_clusters.id"), nullable=False
    )
    dst_cluster_id: Mapped[int] = mapped_column(
        ForeignKey("story_clusters.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # successor|background|duplicate
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("src_cluster_id", "dst_cluster_id", "kind", name="uq_cluster_edge"),
        Index("ix_cluster_edges_src", "src_cluster_id"),
    )


# ── G1: global entity backbone (Wave D Phase 3) ──────────────────────────────────────
# Global, content-scoped (shared across users like articles/clusters) — NOT in _RLS_TABLES.
# Resolution is case-insensitive via normalized columns (*_norm = value.lower()) + plain b-tree
# indexes — avoids functional lower() indexes that trip Alembic autogenerate parity. No embedding
# column in G1 (the NN tie-breaker + auto-merge are deferred to G2).


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)  # display form
    name_norm: Mapped[str] = mapped_column(Text, nullable=False)  # lower(canonical_name) for lookup
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # person|org|place|other (convention)
    description: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mention_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_entities_kind_name", "kind", "name_norm"),  # exact resolution pre-filter
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_norm: Mapped[str] = mapped_column(Text, nullable=False)  # lower(alias)
    source: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("entity_id", "alias_norm", name="uq_entity_alias"),
        Index("ix_entity_aliases_alias", "alias_norm"),
    )


class ArticleEntity(Base):
    __tablename__ = "article_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    salience: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("article_id", "entity_id", name="uq_article_entity"),  # idempotent re-extract
        Index("ix_article_entities_entity", "entity_id"),  # reverse "appears in" lookup
        Index("ix_article_entities_article", "article_id"),  # feed-pool + relevance-scorer join (hot path)
    )


class UserEntityRelevance(Base):
    """G2: per-user affinity on a GLOBAL entity. The only new RLS-scoped table — JOIN/filter only,
    never a graph-per-user. Drives personalized cast-strip ranking. Decay is computed AT READ TIME
    from engagement_raw + last_event_at, so `score` is an optional write-time cache, not the key."""

    __tablename__ = "user_entity_relevance"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # follow | feedback
    engagement_raw: Mapped[float] = mapped_column(Float, server_default="0", nullable=False)
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)  # optional write-time cache (not the ranking key)

    # No extra index: the (user_id, entity_id) PK already serves the personalization join's
    # `WHERE user_id =` (leftmost column). The old ix_uer_user_score on (user_id, score) was dead
    # weight — `score` is never written, so it indexed all-NULL and only cost writes. Re-add a
    # (user_id, score) index if/when score is materialized for a global-ranking query.


# ── Row-Level Security (Wave D Phase A) ──────────────────────────────────────────────
# Per-user tables are isolated by the `app.user_id` GUC, which get_current_user sets per request
# (SET LOCAL). "Enforce-when-set": when the GUC is unset — background jobs reading the owner's API
# key, direct-DB tests — the policy is permissive; when set (every real request) rows are filtered
# to that user. The explicit current_user_id() filter in queries is the PRIMARY control; RLS is
# defense-in-depth. Defined here (DDL events) so create_all (tests) matches the production migration.
_RLS_TABLES = ("user_feedback", "user_preferences", "user_settings", "follows",
               "user_entity_relevance", "impressions")


def rls_statements(table: str) -> list[str]:
    # NULLIF(..., '') treats both an unset GUC (NULL) and an explicitly-cleared one ('') as "no
    # context" → permissive; a real user id filters. (set_config(NULL) yields '' not NULL, and the
    # bare ''::int cast would otherwise error.)
    pred = (
        "NULLIF(current_setting('app.user_id', true), '') IS NULL "
        "OR user_id = NULLIF(current_setting('app.user_id', true), '')::int"
    )
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {table}_user_isolation ON {table}",
        f"CREATE POLICY {table}_user_isolation ON {table} USING ({pred}) WITH CHECK ({pred})",
    ]


def _install_rls_events() -> None:
    for table in _RLS_TABLES:
        tbl = Base.metadata.tables[table]
        for stmt in rls_statements(table):
            event.listen(tbl, "after_create", DDL(stmt))


_install_rls_events()
