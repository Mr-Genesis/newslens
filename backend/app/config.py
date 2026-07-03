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
    # Empty ⇒ DERIVED from database_url (→ psycopg2) in model_post_init. Critical: prod sets only
    # DATABASE_URL, so a non-empty default here would win the `or` below and silently point the sync
    # path (Alembic migrations) at localhost. Set DATABASE_URL_SYNC explicitly only to override.
    database_url_sync: str = ""

    # Schema authority. Local dev / tests bootstrap the schema with Base.metadata.create_all
    # (init_db). PROD is migration-only: the Docker start command runs `alembic upgrade head`, and
    # create_all is DANGEROUS there because it CREATEs missing tables but can never ALTER an existing
    # table to add a new column — which is exactly how the prod schema silently drifted. Set
    # INIT_DB_CREATE_ALL=false in any environment whose schema is owned by Alembic.
    init_db_create_all: bool = True

    def model_post_init(self, __context):
        # Auto-fix database URLs from cloud providers
        self.database_url = _fix_db_url(self.database_url, async_driver=True)
        self.database_url_sync = _fix_db_url(
            self.database_url_sync or self.database_url, async_driver=False
        )

    # OpenAI
    openai_api_key: str = ""

    # LLM generation provider. Default gemini (BYOM; env default, per-user active_provider wins).
    generation_provider: str = "gemini"  # "openai" | "gemini" | "anthropic"
    gemini_api_key: str = ""
    # gemini-2.0-flash was retired for current keys (404 NotFound, same failure vector as
    # text-embedding-004 → see embedding_model below). 2.5-flash is the current GA workhorse;
    # override via GEMINI_MODEL if Google rotates names again.
    gemini_model: str = "gemini-2.5-flash"
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

    # G1 entity backbone (Wave D Phase 3). Extraction is ON by default — it needs a platform LLM key to
    # run and skips gracefully (LLMUnavailable) without one. Set GRAPH_EXTRACTION_ENABLED=false to disable.
    graph_extraction_enabled: bool = True
    graph_extraction_model: str = "gpt-4o-mini"
    graph_max_entities_per_cluster: int = 12   # cast-strip cap + extraction salience cap
    graph_salience_floor: float = 0.3          # drop entities below this salience at extraction
    graph_extract_batch_size: int = 20         # clusters per backfill run
    graph_extract_min_sources: int = 2         # only extract "settled" clusters (>= this many sources)
    graph_extract_research_min_sources: int = 1  # #89: research clusters are singletons → extract at 1
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

    # Phase 1 source expansion — credibility floors for the gated tiers (research/expert). A gated
    # source below the feed floor is discover/search-only; below the briefing floor it never enters
    # the briefing. News sources (NULL credibility) are never floored.
    credibility_feed_floor: int = 55
    credibility_briefing_floor: int = 70
    # Phase 2 · #79 — credibility nudges feed ordering via a bounded multiplier on the rank blend:
    # × (0.9 + 0.2 × score/100) ⇒ ×[0.9, 1.1]. News (NULL credibility) is treated as this neutral
    # score → ×1.0. The ±10% cap means credibility curates ordering but can never drown fresher news.
    credibility_rank_neutral: int = 75
    # #94 — a doctor's OWN specialty gets a bounded feed-rank boost (a cardiologist's cardiology paper
    # over an equal-recency oncology one). Broad `medicine` gating is unchanged — this only re-ranks.
    specialty_rank_boost: float = 1.25
    # Phase 2 · #83 — reserved research/expert slots in the ~25-card discover deck (the opt-in surface).
    discover_gated_slots: int = 5
    # Phase 3 · #90 — a gated source is re-proposed by the monthly LLM review job once its last
    # review is older than this many days (propose-only; a human applies via the admin endpoint).
    credibility_review_stale_days: int = 90
    # #97 — /admin/breadth default staleness window (a source with no article fetched in this many days
    # is "stale"). Overridable per request via ?days=.
    breadth_stale_days: int = 30
    # #98 — discover tension-line lens (a one-line story conflict). Backfilled + cached on
    # extra_json; skips gracefully without a platform LLM key.
    tension_lines_enabled: bool = True
    tension_batch_size: int = 20
    tension_interval_minutes: int = 20
    # Phase 3 · #86 — PubMed personal research feed. E-utilities are usable without a key at a lower
    # rate; an NCBI api_key raises the ceiling to ~10 req/s (we still self-throttle). No key → the
    # job runs unauthenticated (still rate-limited). pubmed_enabled=false disables ingestion.
    ncbi_api_key: str = ""
    pubmed_enabled: bool = True
    pubmed_min_request_interval: float = 0.34  # ≤3 req/s (unauthenticated NCBI limit)
    pubmed_retmax: int = 25                     # papers/specialty/run (mirrors research per_fetch_cap)
    # Phase 2 · #80 — additive story_weights bonus for a persona-matched research/expert cluster, so
    # "research in your field" reliably reaches the briefing top-8 without a singleton dominating.
    credibility_briefing_bonus: float = 0.15
    # Phase 3 (official-sources) — India exchange filings (NSE per-company feeds). The filing tier is
    # watchlist-only: on ingest, a `filing_watchlist`-flagged source keeps only items whose company
    # (matched by name — these feeds carry no symbol) is in the AGGREGATE watchlist, attaches each to
    # its org entity, and the feed shows it only to a user whose OWN watchlist/follows resolve to that
    # entity. Off ⇒ those sources ingest nothing AND the read-path widening is skipped (byte-identical).
    exchange_filings_enabled: bool = True

    # DB SSL: verified by default for cloud (Neon/Supabase). Opt out only if a cert
    # chain genuinely can't be verified in your environment.
    db_ssl_insecure: bool = False

    # Fetch intervals (minutes)
    rss_fetch_interval_minutes: int = 10
    gdelt_fetch_interval_minutes: int = 15
    embedding_backfill_interval_minutes: int = 5

    # GDELT query (parametrized for region/language; default India + English).
    # MUST include at least one keyword term: operator-only queries (e.g. bare "sourcecountry:IN")
    # make the DOC API return a plain-text notice instead of JSON, so ingestion silently drops to
    # zero. sourcelang:eng keeps non-English Indian content out of the English embedding space.
    gdelt_query: str = (
        "(india OR business OR technology OR startup OR economy OR government OR science) "
        "sourcecountry:IN sourcelang:eng"
    )

    # Embedding config — Gemini gemini-embedding-001 (current GA model; text-embedding-004 is retired).
    # It is natively 3072-dim but supports Matryoshka truncation via output_dimensionality, so we
    # request 768 to match the pgvector column (migration a2b3c4d5e6f7). Truncation needs no L2
    # normalization here because clustering/search use cosine distance (scale-invariant). Config-driven
    # so models.py's Vector(embedding_dimensions) and the tests follow automatically; overridable via
    # EMBEDDING_MODEL if Google rotates the model name again.
    embedding_model: str = "models/gemini-embedding-001"
    embedding_dimensions: int = 768
    embedding_task_document: str = "retrieval_document"  # stored article/topic vectors
    embedding_task_query: str = "retrieval_query"        # search-query vectors (asymmetric retrieval)

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
