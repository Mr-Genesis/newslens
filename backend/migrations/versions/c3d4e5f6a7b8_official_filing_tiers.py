"""Official-sources plan: `official` + `filing` SourceType values (no new columns).

official = regulator/central-bank/ministry/exchange notices — audience-gated like research.
filing   = per-company disclosures (EDGAR, NSE/BSE) — watchlist/follow-only, never in discover.

All six Phase-1 credibility columns are reused; this migration only extends the native enum.
`ALTER TYPE ... ADD VALUE` cannot run inside a transaction → autocommit block; IF NOT EXISTS makes
it re-runnable and tolerant of hand-ALTERed dev DBs. Enum values cannot be removed in Postgres —
downgrade is a documented no-op (unused labels are harmless).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'official'")
        op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'filing'")


def downgrade() -> None:
    # Native enum values cannot be dropped without recreating the type; the labels are harmless
    # if unused, so downgrade intentionally does nothing.
    pass
