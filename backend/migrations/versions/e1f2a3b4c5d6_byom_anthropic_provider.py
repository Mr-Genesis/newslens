"""wave E (BYOM): anthropic key trio + active_provider + anthropic_model on user_settings

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-25 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("anthropic_api_key_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column("anthropic_key_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("user_settings", sa.Column("anthropic_key_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_settings", sa.Column("active_provider", sa.String(length=16), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column("model_prefs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    for col in (
        "model_prefs",
        "active_provider",
        "anthropic_key_verified_at",
        "anthropic_key_verified",
        "anthropic_api_key_encrypted",
    ):
        op.drop_column("user_settings", col)
