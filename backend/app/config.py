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

    # LLM generation provider (embeddings stay on OpenAI — see embeddings.py)
    generation_provider: str = "openai"  # "openai" | "gemini" | "anthropic" (env default; per-user active_provider wins)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    # Wave E (BYOM): Anthropic provider. Env key = platform fallback for background jobs.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"  # cheap/fast default; env or per-user override wins

    # Encryption (for storing API keys in DB)
    encryption_key: str = ""
    # When true, refuse to store secrets without an ENCRYPTION_KEY (set in production).
    require_encryption: bool = False

    # Firebase Admin SDK (verifies ID tokens at app/services/auth.py). Supply ONE; if neither is
    # set, token verification is DISABLED and resolve_user falls back to the default user
    # (back-compat dev path). env_prefix="" so the field name IS the env var (uppercased).
    firebase_credentials_json: str = ""          # inline service-account JSON (best for hosted secrets)
    google_application_credentials: str = ""     # path to a mounted service-account .json
    # When true, an unauthenticated request (no Authorization header) is rejected with 401 instead
    # of falling back to the default user. Set AUTH_REQUIRED=true for real multi-user production;
    # default false keeps single-user dev + the rollout window working.
    auth_required: bool = False

    # G1 entity backbone (Wave D Phase 3). Extraction ships DARK (enable after monitoring skip rate).
    graph_extraction_enabled: bool = False
    graph_extraction_model: str = "gpt-4o-mini"
    graph_max_entities_per_cluster: int = 12   # cast-strip cap + extraction salience cap
    graph_salience_floor: float = 0.3          # drop entities below this salience at extraction
    graph_extract_batch_size: int = 20         # clusters per backfill run
    graph_extract_min_sources: int = 2         # only extract "settled" clusters (>= this many sources)
    graph_use_platform_key: bool = True        # extract on the platform key, never the owner's per-user key
    graph_extract_interval_minutes: int = 15   # backfill cadence

    # G2 per-user entity overlay (Wave D Phase 3). Decay/weight constants are HYPOTHESES — no
    # single-user data can tune them; treat as knobs, not validated values.
    # ON by default (cast strip + feed/briefing/search). Safe with no signal: a user with zero
    # relevance rows is a no-op on every surface. Set UER_ENABLED=false to disable.
    uer_enabled: bool = True
    uer_half_life_days: float = 21.0
    uer_follow_weight: float = 1.0
    uer_rank_alpha: float = 0.6   # weight on global salience (cast strip only)
    uer_rank_beta: float = 0.4    # weight on decayed per-user relevance
    # Surface personalization (feed/briefing/search). Multipliers/offsets on the shared cluster
    # relevance score — NOT replacements for the core decay knobs above. Hypothesis-grade; ship dark
    # behind uer_enabled. The cluster score is AVG(decayed relevance) over a cluster's entities, so a
    # zero-relevance user scores 0 everywhere → every surface collapses to its baseline (no-op).
    uer_feed_pool_size: int = 500          # recent-article candidate pool when personalizing the feed
    uer_feed_blend_ratio: float = 0.3      # weight on relevance vs recency in the feed blend [0..1]
    uer_briefing_blend_weight: float = 0.2  # additive scaler on cluster relevance into story_weights
    uer_search_rerank_boost: float = 10.0   # max within-tier rank improvement (must stay < the 100 gap)
    uer_search_relevance_threshold: float = 0.3  # min relevance before any search boost applies

    # DB SSL: verified by default for cloud (Neon/Supabase). Opt out only if a cert
    # chain genuinely can't be verified in your environment.
    db_ssl_insecure: bool = False

    # Fetch intervals (minutes)
    rss_fetch_interval_minutes: int = 10
    gdelt_fetch_interval_minutes: int = 15
    embedding_backfill_interval_minutes: int = 5

    # GDELT query (parametrized for region/language; default India + English)
    gdelt_query: str = "sourcecountry:IN"

    # Embedding config
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Summary config
    summary_model: str = "gpt-4o-mini"
    summary_batch_size: int = 5

    # Impact engine v2 (Wave A): structured + validated + guarded WIIFM.
    # Flip off to fall back to the legacy free-text impact lens.
    impact_v2_enabled: bool = True
    impact_max_tokens: int = 900          # spec §8 (vs the 800 default for other lenses)
    impact_cache_ttl_hours: int = 24      # spec §4

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
