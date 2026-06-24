"""follows: standing follows (topics, entities, saved searches)

Revision ID: c2a3b4d5e6f7
Revises: b1f0a2c3d4e5
Create Date: 2026-06-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c2a3b4d5e6f7"
down_revision: Union[str, None] = "b1f0a2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "follows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "kind", "value", name="uq_follow_user_kind_value"
        ),
    )
    op.create_index("ix_follows_user_id", "follows", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_follows_user_id", table_name="follows")
    op.drop_table("follows")
