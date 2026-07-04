"""WS-5 (#115): entity_edges — global co-occurrence graph.

Two entities that shared a story cluster get a decayed-weight edge (both directions). The nightly job
upserts and keeps the top-K per source; one-hop interest expansion reads `WHERE src_entity_id IN
(...)`, served by the composite PK's leftmost column (no extra index — mirrors user_entity_relevance).
Global / content-scoped: NOT RLS.

Revision ID: f6a7b8c9dae5
Revises: e5f6a7b8c9da
"""
import sqlalchemy as sa

from alembic import op

revision = "f6a7b8c9dae5"
down_revision = "e5f6a7b8c9da"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_edges",
        sa.Column("src_entity_id", sa.Integer(), nullable=False),
        sa.Column("dst_entity_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["src_entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dst_entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("src_entity_id", "dst_entity_id"),
    )


def downgrade() -> None:
    op.drop_table("entity_edges")
