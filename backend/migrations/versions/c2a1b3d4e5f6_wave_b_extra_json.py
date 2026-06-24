"""wave B: story_clusters.extra_json (frameworks + consensus cache)

Revision ID: c2a1b3d4e5f6
Revises: b1f0a2c3d4e5
Create Date: 2026-06-24 04:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c2a1b3d4e5f6"
down_revision: Union[str, None] = "b1f0a2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "story_clusters",
        sa.Column("extra_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("story_clusters", "extra_json")
