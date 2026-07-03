"""One-time backfill: decode HTML entities in already-ingested rows.

The fetcher now html.unescape()s titles/snippets at ingestion, but rows ingested before that fix
still carry raw entities (&nbsp; &#8377; &amp;) in the DB — visible on cards and in fallback
summaries. This decodes them in place. Idempotent: unescaping already-clean text is a no-op, and
the WHERE prefilter skips rows without an entity-looking pattern.

Run inside the backend container/image with DATABASE_URL set (same env as the app):

    python scripts/unescape_articles.py
"""
import asyncio
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

from sqlalchemy import text  # noqa: E402

from app.database import async_session  # noqa: E402

# (table, [columns]) — only text the UI/summaries surface. Prefilter keeps churn minimal.
TARGETS = [
    ("articles", ["title", "snippet", "extracted_text"]),
    ("story_clusters", ["title", "summary"]),
]
# Matches &word; / &#123; style sequences cheaply in SQL to prefilter candidate rows.
ENTITY_LIKE = "'%&%;%'"


async def main() -> None:
    total = 0
    async with async_session() as session:
        for table, columns in TARGETS:
            for col in columns:
                rows = (
                    await session.execute(
                        text(
                            f"SELECT id, {col} FROM {table} "
                            f"WHERE {col} IS NOT NULL AND {col} LIKE {ENTITY_LIKE}"
                        )
                    )
                ).all()
                changed = 0
                for row_id, value in rows:
                    decoded = html.unescape(value)
                    if decoded != value:
                        await session.execute(
                            text(f"UPDATE {table} SET {col} = :v WHERE id = :id"),
                            {"v": decoded, "id": row_id},
                        )
                        changed += 1
                total += changed
                print(f"{table}.{col}: {len(rows)} candidates, {changed} updated")
        await session.commit()
    print(f"done — {total} values decoded")


if __name__ == "__main__":
    asyncio.run(main())
