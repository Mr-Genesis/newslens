"""Calibrate cluster_similarity_threshold from REAL doc↔doc distances.

Clustering joins an article to a cluster iff its cosine distance to some already-clustered article is
< cluster_similarity_threshold (0.15). Nobody has ever measured the actual nearest-neighbour distance
distribution of this corpus — 0.15 was set in the initial scaffold and never tuned. This samples
recent embedded articles, finds each one's nearest OTHER article, and histograms the distances. If a
lot of mass sits in 0.15–0.30, the threshold is too strict and same-event pairs are being split into
separate clusters. Set the threshold at the valley before the off-topic tail.

Mirrors scripts/measure_follow_distances.py (which does the query↔doc side for rails). This side needs
NO Gemini key — it reads stored document vectors directly. RUN AFTER a re-embed (scripts/reembed.py),
so the vectors reflect the current embed recipe. See docs/fixes/follow-rails-identical-rootcause.md.

RUN (needs DB access only):
    cd backend
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.measure_cluster_distances --sample 300
"""
import argparse
import asyncio
import statistics

from sqlalchemy import text

from app.config import settings
from app.database import async_session

CANDIDATE_THRESHOLDS = (0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30)


async def _nearest_other_distances(session, sample: int, window_hours: int | None) -> list[float]:
    """For each of the newest `sample` embedded articles, the cosine distance to its nearest OTHER
    embedded article. One indexed ORDER BY … LIMIT 1 per sampled row."""
    where_window = ""
    params: dict = {"sample": sample}
    if window_hours:
        where_window = "AND fetched_at >= now() - (:hrs || ' hours')::interval"
        params["hrs"] = window_hours
    ids = (
        await session.execute(
            text(
                f"SELECT id FROM articles WHERE embedding IS NOT NULL {where_window} "
                "ORDER BY fetched_at DESC LIMIT :sample"
            ),
            params,
        )
    ).scalars().all()

    dists: list[float] = []
    for aid in ids:
        row = (
            await session.execute(
                text(
                    "SELECT b.embedding <=> (SELECT embedding FROM articles WHERE id = :aid) AS dist "
                    "FROM articles b "
                    "WHERE b.embedding IS NOT NULL AND b.id <> :aid "
                    "ORDER BY dist LIMIT 1"
                ),
                {"aid": aid},
            )
        ).first()
        if row is not None and row[0] is not None:
            dists.append(float(row[0]))
    return dists


def _report(dists: list[float]) -> None:
    if not dists:
        print("no embedded articles in scope — run after some articles have embedded.")
        return
    dists = sorted(dists)
    n = len(dists)
    p = lambda frac: dists[min(n - 1, int(frac * n))]  # noqa: E731 — tiny local percentile
    print(
        f"n={n}  min={dists[0]:.3f}  p10={p(0.10):.3f}  p25={p(0.25):.3f}  "
        f"p50={p(0.50):.3f}  p75={p(0.75):.3f}  max={dists[-1]:.3f}"
    )
    print(f"current cluster_similarity_threshold = {settings.cluster_similarity_threshold}\n")
    print("nearest-neighbour pairs that WOULD merge at each candidate threshold:")
    for t in CANDIDATE_THRESHOLDS:
        c = sum(d < t for d in dists)
        marker = "  <- current" if abs(t - settings.cluster_similarity_threshold) < 1e-9 else ""
        print(f"  < {t:.2f} : {c:4d} / {n}  ({100 * c / n:5.1f}%){marker}")
    band = sum(settings.cluster_similarity_threshold <= d < 0.30 for d in dists)
    print(
        f"\nnear-miss band [{settings.cluster_similarity_threshold:.2f}, 0.30): {band} pairs "
        f"({100 * band / n:.1f}%) — these are candidate same-event pairs the current bar rejects."
    )
    print("Calibrate: set the threshold at the valley before the off-topic tail (watch p50/p75).")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Histogram doc↔doc nearest-neighbour distances.")
    parser.add_argument("--sample", type=int, default=300, help="how many recent articles to probe")
    parser.add_argument(
        "--window-hours", type=int, default=0, help="restrict the sample to the last N hours (0 = all time)"
    )
    args = parser.parse_args()
    async with async_session() as session:
        dists = await _nearest_other_distances(session, args.sample, args.window_hours or None)
    _report(dists)


if __name__ == "__main__":
    asyncio.run(main())
