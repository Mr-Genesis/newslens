from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://newslens:newslens_dev@localhost:5432/newslens"
    database_url_sync: str = "postgresql://newslens:newslens_dev@localhost:5432/newslens"

    # OpenAI
    openai_api_key: str = ""

    # Encryption (for storing API keys in DB)
    encryption_key: str = ""

    # Fetch intervals (minutes)
    rss_fetch_interval_minutes: int = 10
    gdelt_fetch_interval_minutes: int = 15
    embedding_backfill_interval_minutes: int = 5

    # Embedding config
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Summary config
    summary_model: str = "gpt-4o-mini"
    summary_batch_size: int = 5

    # Clustering
    cluster_similarity_threshold: float = 0.15  # cosine distance (1 - similarity)
    new_topic_max_similarity: float = 0.6

    # Recommendation
    default_explore_ratio: float = 0.3
    min_explore_ratio: float = 0.1
    max_explore_ratio: float = 0.5
    feedback_window_size: int = 50

    # Dedup
    title_similarity_threshold: float = 0.9

    # Content quality
    min_snippet_length: int = 50

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


settings = Settings()
