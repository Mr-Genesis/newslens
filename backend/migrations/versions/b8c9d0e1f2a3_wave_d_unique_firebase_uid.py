"""wave D phase A: unique index on users.firebase_uid

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-24 12:30:00.000000

Postgres allows multiple NULLs in a unique index, so the default user (id=1) and any legacy rows
keep firebase_uid = NULL without conflict; only real Firebase uids are forced unique. This closes
the get-or-create race that could otherwise create two User rows for one Firebase account.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("uq_users_firebase_uid", "users", ["firebase_uid"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_firebase_uid", table_name="users")
