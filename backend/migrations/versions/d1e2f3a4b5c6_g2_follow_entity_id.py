"""g2: follows.entity_id (persist the resolved entity behind an entity-follow)

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-26 09:30:00.000000

Nullable add keeps uq_follow(user_id,kind,value) live — no orphan window.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("follows", sa.Column("entity_id", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "follows", "entities", ["entity_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_follows_entity", "follows", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_follows_entity", table_name="follows")
    op.drop_constraint("follows_entity_id_fkey", "follows", type_="foreignkey")
    op.drop_column("follows", "entity_id")
