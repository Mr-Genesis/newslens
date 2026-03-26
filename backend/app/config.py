from pydantic_settings import BaseSettings


def _fix_db_url(url: str, async_driver: bool = True) -> str:
    """Normalize DATABASE_URL for SQLAlchemy.
    Render/Fly/Neon provide postgres:// or postgresql://, we need postgresql+asyncpg://.
    Also strips params unsupported by asyncpg (e.g. channel_binding from Neon).
    """
    # Strip query params that break asyncpg via SQLAlchemy
    # SSL is handled via connect_args in database.py instead
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params.pop("channel_binding", None)
    if async_driver:
        params.pop("sslmode", None)
        params.pop("ssl", None)
    clean_query = urlencode(params, doseq=True)
    url = urlunparse(parsed._replace(query=clean_query))

    if async_driver:
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return url.replace(prefix, "postgresql+asyncpg://", 1)
    else:
        for prefix in ("postgres://", "postgresql+asyncpg://"):
            if url.startswith(prefix):
                return url.replace(prefix, "postgresql://", 1)
    return url


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://newslens:newslens_dev@localhost:5432/newslens"
    database_url_sync: str = "postgresql://newslens:newslens_dev@localhost:5432/newslens"

    def model_post_init(self, __context):
        # Auto-fix database URLs from cloud providers
        self.database_url = _fix_db_url(self.database_url, async_driver=True)
        self.database_url_sync = _fix_db_url(
            self.database_url_sync or self.database_url, async_driver=False
        )

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
