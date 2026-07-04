"""WS-2 (#112) PRE-GATE: measure real query->article cosine distances so the rails precision
thresholds (rails_dist_loose / rails_dist_tight) are CALIBRATED, not guessed.

Query embeddings (RETRIEVAL_QUERY) and document embeddings (RETRIEVAL_DOCUMENT) have their own
distance distribution — clustering's 0.15 doc<->doc threshold does NOT transfer, and nobody has ever
observed a query<->article distance in this system (search discards it). This script logs the
distribution for a handful of representative phrases against the live corpus.

RUN (needs a Gemini key + DB access — the CI harness mocks embeddings, so this is a manual tool):
    cd backend
    GEMINI_API_KEY=... DATABASE_URL=postgresql+asyncpg://... python -m scripts.measure_follow_distances

Read the output: for a GOOD phrase ("US Iran war"), the true matches cluster at low distance and there
is a visible gap before the off-topic tail — set rails_dist_tight just below the on-topic cluster and
rails_dist_loose at the gap. For a BROAD phrase ("AI"), expect no gap (that's why the keyword/entity
confirmation leg exists). The rails endpoint ALSO logs `rail_distance_histogram` per eval in prod, so
these thresholds keep self-reporting once live.
"""
import asyncio
import statistics

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.services.embeddings import embed_query_cached, vector_literal

PHRASES = [
    "US Iran war",
    "AI chip supply chain",
    "Russia Ukraine war",
    "UK politics",
    "South Korea stock market",
    "AI innovations",
    "Reliance Industries earnings",
    "cricket world cup",
    "climate policy",
    "Federal Reserve interest rates",
]


async def _distances(session: AsyncSession, phrase: str, k: int = 100) -> list[float]:
    emb = await embed_query_cached(phrase)
    if emb is None:
        return []
    rows = (
        await session.execute(
            text(
                "SELECT embedding <=> :v AS dist FROM articles "
                "WHERE embedding IS NOT NULL AND published_at >= now() - interval '72 hours' "
                "ORDER BY embedding <=> :v LIMIT :k"
            ),
            {"v": vector_literal(emb), "k": k},
        )
    ).all()
    return [float(d) for (d,) in rows]


def _fmt(ds: list[float]) -> str:
    if not ds:
        return "no embedded articles in window"
    ds = sorted(ds)
    q = statistics.quantiles(ds, n=20) if len(ds) >= 20 else ds
    return (
        f"n={len(ds)}  min={ds[0]:.3f}  p5={q[0]:.3f}  p25={ds[len(ds)//4]:.3f} "
        f"p50={ds[len(ds)//2]:.3f}  max={ds[-1]:.3f}  "
        f"<tight({settings.rails_dist_tight})={sum(d < settings.rails_dist_tight for d in ds)}  "
        f"<loose({settings.rails_dist_loose})={sum(d < settings.rails_dist_loose for d in ds)}"
    )


async def main() -> None:
    print(f"Current thresholds: tight={settings.rails_dist_tight}  loose={settings.rails_dist_loose}\n")
    async with async_session() as session:
        for phrase in PHRASES:
            ds = await _distances(session, phrase)
            print(f"{phrase:32s} {_fmt(ds)}")
    print("\nCalibrate: tight = just below each on-topic cluster; loose = the gap before the off-topic tail.")


if __name__ == "__main__":
    asyncio.run(main())
