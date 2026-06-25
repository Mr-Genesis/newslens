"""wave D phase A: row-level security on per-user tables

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-25 09:00:00.000000

Mirrors the DDL events in app/models.py (so create_all-built test schema matches prod). Policies
are "enforce-when-set": permissive when app.user_id is unset (background jobs / direct DB), filtered
to that user when set (every real request via get_current_user). RLS is defense-in-depth on top of
the explicit current_user_id() filter in the route queries.
"""
from typing import Sequence, Union

from alembic import op

from app.models import _RLS_TABLES, rls_statements

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in _RLS_TABLES:
        for stmt in rls_statements(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_user_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
