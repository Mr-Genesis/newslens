"""Phase 1 source expansion: research/expert enum values + credibility/persona columns.

Adds two persona-gated SourceType values ('research', 'expert') and six additive, nullable
columns on `sources` that carry the credibility + audience metadata for the gated tiers:
author_name, credibility_score, credibility_meta, audience, is_preprint, per_fetch_cap.

`ALTER TYPE ... ADD VALUE` cannot run inside a transaction block, so the enum values are added in
an autocommit block *before* the column DDL. Everything is additive — no data migration, and the
pre-expansion feed is byte-identical until sources.json seeds the new tiers.

Revision ID: b2c3d4e5f6a7
Revises: a2b3c4d5e6f7
Create Date: 2026-07-03 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Extend the native enum. ADD VALUE is non-transactional; IF NOT EXISTS makes it re-runnable.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'research'")
        op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'expert'")

    # 2) Additive credibility/persona columns (all nullable except is_preprint, which defaults false).
    op.add_column("sources", sa.Column("author_name", sa.String(length=255), nullable=True))
    op.add_column("sources", sa.Column("credibility_score", sa.SmallInteger(), nullable=True))
    op.add_column("sources", sa.Column("credibility_meta", JSONB(), nullable=True))
    op.add_column("sources", sa.Column("audience", sa.ARRAY(sa.String()), nullable=True))
    op.add_column(
        "sources",
        sa.Column("is_preprint", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("sources", sa.Column("per_fetch_cap", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    # Drop the columns. Native enum values cannot be removed in Postgres without recreating the
    # type; the two extra labels are harmless if left in place, so downgrade only reverts columns.
    op.drop_column("sources", "per_fetch_cap")
    op.drop_column("sources", "is_preprint")
    op.drop_column("sources", "audience")
    op.drop_column("sources", "credibility_meta")
    op.drop_column("sources", "credibility_score")
    op.drop_column("sources", "author_name")
