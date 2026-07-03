"""Move embeddings to Gemini text-embedding-004: pgvector column 1536 -> 768 + re-embed.

Old OpenAI 1536-dim vectors live in a different embedding space and cannot be reused, so this clears
all stored embeddings (articles reset to 'pending' so the backfill re-embeds them with Gemini; topic
embeddings re-seed on next startup) and resizes the pgvector columns. The HNSW index is dropped and
recreated because it is bound to the column dimension.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HNSW = "ix_articles_embedding_hnsw"


def _resize(dim: int) -> None:
    # 1) Drop the dimension-bound HNSW index before altering the column type.
    op.execute(f"DROP INDEX IF EXISTS {_HNSW}")
    # 2) Clear vectors from the old space (only possible to resize once every value is NULL).
    #    Articles go back to 'pending' so the embedding backfill re-embeds; topics re-seed on startup.
    op.execute(
        "UPDATE articles SET embedding = NULL, embedding_status = 'pending' "
        "WHERE embedding IS NOT NULL"
    )
    op.execute("UPDATE topics SET embedding = NULL WHERE embedding IS NOT NULL")
    # 3) Resize the pgvector columns.
    op.execute(f"ALTER TABLE articles ALTER COLUMN embedding TYPE vector({dim})")
    op.execute(f"ALTER TABLE topics   ALTER COLUMN embedding TYPE vector({dim})")
    # 4) Recreate the cosine HNSW index at the new dimension.
    op.execute(f"CREATE INDEX {_HNSW} ON articles USING hnsw (embedding vector_cosine_ops)")


def upgrade() -> None:
    _resize(768)   # Gemini text-embedding-004


def downgrade() -> None:
    _resize(1536)  # OpenAI text-embedding-3-small (vectors are cleared, not restored)
