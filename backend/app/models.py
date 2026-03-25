import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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


class SourceType(str, enum.Enum):
    newspaper = "newspaper"
    blog = "blog"
    channel = "channel"
    wire = "wire"
    other = "other"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    feedback: Mapped[list["UserFeedback"]] = relationship(back_populates="user")
    preferences: Mapped[list["UserPreference"]] = relationship(back_populates="user")


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    articles: Mapped[list["Article"]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="feedback")
    article: Mapped["Article"] = relationship(back_populates="feedback")


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
