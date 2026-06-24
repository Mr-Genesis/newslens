"""wave D2: cluster_edges (how we got here)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-24 11:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cluster_edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("src_cluster_id", sa.Integer(), nullable=False),
        sa.Column("dst_cluster_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["src_cluster_id"], ["story_clusters.id"]),
        sa.ForeignKeyConstraint(["dst_cluster_id"], ["story_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("src_cluster_id", "dst_cluster_id", "kind", name="uq_cluster_edge"),
    )
    op.create_index("ix_cluster_edges_src", "cluster_edges", ["src_cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_cluster_edges_src", table_name="cluster_edges")
    op.drop_table("cluster_edges")
