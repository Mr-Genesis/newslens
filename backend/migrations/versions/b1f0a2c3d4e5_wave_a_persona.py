"""wave A: richer persona (watchlist, region, depth_pref, persona_version)

Revision ID: b1f0a2c3d4e5
Revises: f76aec9da324
Create Date: 2026-06-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1f0a2c3d4e5"
down_revision: Union[str, None] = "f76aec9da324"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("watchlist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("users", sa.Column("region", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "depth_pref", sa.String(length=16), server_default="standard", nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column("persona_version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "persona_version")
    op.drop_column("users", "depth_pref")
    op.drop_column("users", "region")
    op.drop_column("users", "watchlist")
