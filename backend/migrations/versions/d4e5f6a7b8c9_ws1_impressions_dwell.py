"""WS-1 (#111): impressions table + dwell/surface on user_feedback + articles sort indexes.

- impressions: what a user SAW per surface — deduped per (user, story, surface, day) via a COALESCE
  expression unique index (cluster_id/article_id are nullable; plain NULLs never conflict). `day` is
  a stored DATE column because date(created_at) over timestamptz is not IMMUTABLE in Postgres.
- user_feedback.duration_ms + surface: dwell rides the auto-read row (GREATEST upsert); surface is
  the CTR numerator that pairs with impressions' denominator.
- articles indexes: plain b-trees on published_at + fetched_at — the as_of cursor (WS-3) and rails
  recency windows (WS-2) add range predicates on these columns; added once, here.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
import sqlalchemy as sa

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "impressions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "cluster_id",
            sa.Integer(),
            sa.ForeignKey("story_clusters.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("surface", sa.String(length=16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "cluster_id IS NOT NULL OR article_id IS NOT NULL", name="ck_impression_target"
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_impression_day ON impressions "
        "(user_id, COALESCE(cluster_id, 0), COALESCE(article_id, 0), surface, day)"
    )
    op.create_index("ix_impressions_user_created", "impressions", ["user_id", "created_at"])

    # RLS — same enforce-when-set policy as every per-user table (models.rls_statements).
    from app.models import rls_statements

    for stmt in rls_statements("impressions"):
        op.execute(stmt)

    op.add_column("user_feedback", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("user_feedback", sa.Column("surface", sa.String(length=16), nullable=True))

    # Plain b-tree (not DESC expression) — matches the model declaration so autogenerate parity
    # holds; serves the rails 72h recency window + the as_of cursor range predicates.
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
    op.create_index("ix_articles_fetched_at", "articles", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_articles_fetched_at", table_name="articles")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_column("user_feedback", "surface")
    op.drop_column("user_feedback", "duration_ms")
    op.drop_table("impressions")
