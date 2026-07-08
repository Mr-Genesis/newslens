"""Re-embed the article corpus after an embed-recipe change (embedding_body_chars).

Old vectors (title + snippet[:300]) and new vectors (title + bounded body) live in DIFFERENT spaces,
so until the corpus is re-embedded, old↔new cosine distances are meaningless and clustering / rails /
search stay half-broken. This marks `complete` articles back to `pending`; the running backend's
5-min embedding backfill then re-embeds them under the current recipe — quota-aware (free-tier
~1,000/day, 30-min cooldown after a 429), so a large corpus drains over several days. That is
expected; nothing here bypasses the quota guard. See docs/fixes/follow-rails-identical-rootcause.md.

Marking pending does NOT delete the old vector (the backfill overwrites it), so search/rails keep
working on the old vector until each row is re-embedded. Note: already-clustered articles are NOT
re-clustered by this (placement is permanent) — reconciling the existing split backlog needs the
Phase-3 merge pass or a one-off re-cluster.

RUN (needs DB access; no Gemini key required — this only flips status):
    cd backend
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.reembed --dry-run
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.reembed              # all complete rows
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.reembed --limit 200  # newest 200 first (smoke test)
"""
import argparse
import asyncio

from sqlalchemy import func, select, update

from app.database import async_session
from app.models import Article, EmbeddingStatus


async def _counts(session) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Article.embedding_status, func.count()).group_by(Article.embedding_status)
        )
    ).all()
    return {str(getattr(s, "value", s)): n for s, n in rows}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Re-embed articles after an embed-recipe change.")
    parser.add_argument("--dry-run", action="store_true", help="report counts, change nothing")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="only re-queue the newest N complete rows (0 = all). Useful for a controlled smoke test.",
    )
    args = parser.parse_args()

    async with async_session() as session:
        before = await _counts(session)
        complete = before.get(EmbeddingStatus.complete.value, 0)
        print(f"embedding_status before: {before}")
        target = complete if args.limit <= 0 else min(args.limit, complete)
        print(f"would re-queue {target} 'complete' article(s) → 'pending'"
              + ("" if args.limit <= 0 else f" (newest {args.limit})"))

        if args.dry_run or target == 0:
            print("dry-run — no changes." if args.dry_run else "nothing to do.")
            return

        if args.limit and args.limit > 0:
            ids = (
                await session.execute(
                    select(Article.id)
                    .where(Article.embedding_status == EmbeddingStatus.complete)
                    .order_by(Article.fetched_at.desc())
                    .limit(args.limit)
                )
            ).scalars().all()
            stmt = (
                update(Article)
                .where(Article.id.in_(ids))
                .values(embedding_status=EmbeddingStatus.pending)
            )
        else:
            stmt = (
                update(Article)
                .where(Article.embedding_status == EmbeddingStatus.complete)
                .values(embedding_status=EmbeddingStatus.pending)
            )
        result = await session.execute(stmt)
        await session.commit()
        print(f"re-queued {result.rowcount} row(s) → pending. The backfill will drain them (quota-bound).")
        print(f"embedding_status after: {await _counts(session)}")


if __name__ == "__main__":
    asyncio.run(main())
