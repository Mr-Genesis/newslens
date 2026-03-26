# Architecture — NewsLens

## System Overview

NewsLens is a two-language AI news intelligence platform: Python backend (data pipeline + ML) and TypeScript frontend (UI), communicating via REST JSON. Mobile builds use Capacitor to wrap the frontend into a native Android WebView.

## System Diagram

```mermaid
graph TB
    subgraph "Data Sources"
        RSS[RSS Feeds]
        GDELT[GDELT API]
    end

    subgraph "Backend (FastAPI)"
        subgraph "Fetchers (APScheduler)"
            RF[RSS Fetcher<br/>every 10min]
            GF[GDELT Fetcher<br/>every 15min]
            EB[Embedding Backfill<br/>every 5min]
            CL[Clustering<br/>every 10min]
        end

        subgraph "Services"
            DEDUP[Dedup Service<br/>URL + rapidfuzz]
            EMB[Embedding Service<br/>OpenAI text-embedding-3-small]
            CLUST[Clustering Service<br/>pgvector cosine distance]
            ENC[Encryption Service<br/>Fernet]
        end

        subgraph "API Layer"
            ROUTES[FastAPI Routes<br/>12 endpoints]
        end
    end

    subgraph "Database"
        PG[(PostgreSQL + pgvector)]
    end

    subgraph "Frontend (Next.js 16)"
        subgraph "Pages"
            BRIEF[Briefing /]
            DISC[Discover /discover]
            DEEP[Deep Dive /story]
            SETT[Settings /settings]
        end

        subgraph "Components"
            SC[StoryCard]
            DC[DiscoverCard]
            DDV[DeepDiveView]
            NAV[NavBar]
        end

        API_CLIENT[API Client<br/>lib/api.ts]
    end

    subgraph "Mobile"
        CAP[Capacitor]
        APK[Android APK]
    end

    RSS --> RF
    GDELT --> GF
    RF --> DEDUP --> PG
    GF --> DEDUP
    EB --> EMB --> PG
    CL --> CLUST --> PG
    PG --> ROUTES
    ROUTES --> API_CLIENT
    API_CLIENT --> BRIEF & DISC & DEEP & SETT
    BRIEF --> SC
    DISC --> DC
    DEEP --> DDV
    BRIEF & DISC & DEEP & SETT --> NAV
    API_CLIENT --> CAP --> APK
```

## Data Pipeline Flow

```mermaid
sequenceDiagram
    participant RSS as RSS Feeds
    participant GDELT as GDELT API
    participant Fetch as Fetcher Service
    participant Dedup as Dedup Service
    participant DB as PostgreSQL
    participant Embed as Embedding Service
    participant Cluster as Clustering Service
    participant API as FastAPI Routes
    participant UI as Frontend

    loop Every 10 min
        RSS->>Fetch: feedparser parse
        Fetch->>Dedup: URL + title check
        Dedup->>DB: INSERT articles (embedding_status=pending)
    end

    loop Every 15 min
        GDELT->>Fetch: API query + trafilatura extract
        Fetch->>Dedup: URL + title check
        Dedup->>DB: INSERT articles (embedding_status=pending)
    end

    loop Every 5 min
        DB->>Embed: SELECT WHERE embedding_status IN (pending, failed)
        Embed->>Embed: OpenAI text-embedding-3-small
        Embed->>DB: UPDATE embedding + status=complete
    end

    loop Every 10 min
        DB->>Cluster: SELECT articles with embeddings
        Cluster->>Cluster: pgvector cosine distance < 0.15
        Cluster->>DB: INSERT/UPDATE story_clusters
    end

    UI->>API: GET /briefing, /discover/deck, /clusters/{id}
    API->>DB: Query clusters + articles
    DB->>API: Results
    API->>UI: JSON response
```

## Database Schema

```mermaid
erDiagram
    users {
        int id PK
        timestamp created_at
    }

    sources {
        int id PK
        string name
        string url UK
        string rss_url
        enum source_type "newspaper|blog|channel|wire|other"
        bool is_paywalled
        timestamp created_at
    }

    articles {
        int id PK
        string title
        text snippet
        string url
        int source_id FK
        timestamp published_at
        timestamp fetched_at
        enum embedding_status "pending|complete|failed"
        vector_1536 embedding
    }

    topics {
        int id PK
        string name UK
        int parent_topic_id FK
        vector_1536 embedding
        timestamp created_at
    }

    article_topics {
        int id PK
        int article_id FK
        int topic_id FK
        float relevance_score
    }

    story_clusters {
        int id PK
        string title
        text summary
        timestamp created_at
    }

    cluster_articles {
        int id PK
        int cluster_id FK
        int article_id FK
    }

    user_feedback {
        int id PK
        int user_id FK
        int article_id FK
        enum feedback_type "interesting|less|save|share"
        timestamp created_at
    }

    user_preferences {
        int id PK
        int user_id FK
        int topic_id FK
        float weight
        float breadth_score
    }

    user_settings {
        int id PK
        int user_id FK
        text openai_api_key_encrypted
        bool openai_key_verified
        timestamp openai_key_verified_at
        timestamp updated_at
    }

    users ||--o{ user_feedback : has
    users ||--o{ user_preferences : has
    users ||--o| user_settings : has
    sources ||--o{ articles : publishes
    articles ||--o{ article_topics : tagged
    topics ||--o{ article_topics : contains
    topics ||--o{ topics : parent
    articles ||--o{ cluster_articles : grouped
    story_clusters ||--o{ cluster_articles : contains
    articles ||--o{ user_feedback : receives
    topics ||--o{ user_preferences : weighted
```

**pgvector columns:** `articles.embedding` and `topics.embedding` are `Vector(1536)` for OpenAI text-embedding-3-small. Clustering uses cosine distance with threshold 0.15.

## Capacitor Build Pipeline

```mermaid
flowchart LR
    A[next.config.ts<br/>BUILD_TARGET=capacitor] --> B[next build --webpack<br/>output: export]
    B --> C[Static HTML/JS/CSS<br/>in frontend/out/]
    C --> D[npx cap sync android<br/>Copy to WebView]
    D --> E[gradlew assembleDebug<br/>Build APK]
    E --> F[app-debug.apk<br/>4.75 MB]
```

Web builds use `rewrites()` to proxy `/api/*` to the backend. Capacitor builds use `NEXT_PUBLIC_API_BASE_URL` env var to point directly to the backend host.

## Decision Log

| Decision | Chosen | Alternative | Rationale |
|----------|--------|-------------|-----------|
| Clustering | pgvector cosine distance SQL | Python pairwise comparison | O(n) vs O(n²); DB-native; no data transfer overhead |
| Scheduler | APScheduler in-process | Celery + Redis | Simpler for single-process MVP; no extra infrastructure |
| Title dedup | rapidfuzz | python-Levenshtein | 10-100x faster; pure C implementation; better API |
| DB driver | asyncpg | psycopg2 | Preserves FastAPI's async benefits; native async protocol |
| Frontend framework | Next.js App Router | Vite + React Router | SSR capability; file-based routing; built-in optimizations |
| Mobile | Capacitor static export | React Native rewrite | Zero code duplication; wraps existing web app; 4.75 MB APK |
| API proxy | Next.js rewrites | CORS headers | No CORS configuration needed; single origin in dev |
| Encryption | Fernet (symmetric) | RSA / AES-GCM | Simple, battle-tested; good for per-user key storage |
| CSS | Tailwind CSS 4 | CSS Modules / styled-components | Utility-first; design token integration; small bundle |
| Motion | Framer Motion | CSS animations | Complex gesture physics (swipe cards); declarative API |
