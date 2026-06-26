"""g2: user_entity_relevance overlay (RLS-scoped)

Revision ID: c0d1e2f3a4b5
Revises: e1f2a3b4c5d6
Create Date: 2026-06-26 09:00:00.000000

The only new RLS-scoped table — mirrors the c9d0e1f2a3b4 RLS migration via rls_statements().
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models import rls_statements

revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_entity_relevance",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("engagement_raw", sa.Float(), server_default="0", nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "entity_id"),
    )
    op.create_index("ix_uer_user_score", "user_entity_relevance", ["user_id", "score"])
    for stmt in rls_statements("user_entity_relevance"):
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_entity_relevance_user_isolation ON user_entity_relevance")
    op.execute("ALTER TABLE user_entity_relevance NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_entity_relevance DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_uer_user_score", table_name="user_entity_relevance")
    op.drop_table("user_entity_relevance")
