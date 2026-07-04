"""WS-2 (#112): follows.last_viewed_at — per-follow badge clock.

new_count on a "News You Follow" rail = stories newer than this timestamp. Per-follow (the global
User.last_seen_at can't work — /digest resets it on every read, and one timestamp can't express
per-rail counts). NULL = never viewed.

Revision ID: e5f6a7b8c9da
Revises: d4e5f6a7b8c9
"""
import sqlalchemy as sa

from alembic import op

revision = "e5f6a7b8c9da"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("follows", sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("follows", "last_viewed_at")
