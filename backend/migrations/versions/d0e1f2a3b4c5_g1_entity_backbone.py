"""g1: entity backbone (entities, entity_aliases, article_entities)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-25 12:00:00.000000

Global, content-scoped tables (shared like articles/clusters) — NOT RLS-scoped. Case-insensitive
resolution via normalized *_norm columns + plain b-tree indexes. No embedding column in G1.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("name_norm", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mention_count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entities_kind_name", "entities", ["kind", "name_norm"])

    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("alias_norm", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "alias_norm", name="uq_entity_alias"),
    )
    op.create_index("ix_entity_aliases_alias", "entity_aliases", ["alias_norm"])

    op.create_table(
        "article_entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("salience", sa.Float(), server_default="0", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "entity_id", name="uq_article_entity"),
    )
    op.create_index("ix_article_entities_entity", "article_entities", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_article_entities_entity", table_name="article_entities")
    op.drop_table("article_entities")
    op.drop_index("ix_entity_aliases_alias", table_name="entity_aliases")
    op.drop_table("entity_aliases")
    op.drop_index("ix_entities_kind_name", table_name="entities")
    op.drop_table("entities")
