"""index cleanup: drop dead ix_uer_user_score, add ix_article_entities_article

Revision ID: f1a2b3c4d5e6
Revises: d1e2f3a4b5c6
Create Date: 2026-06-27 10:00:00.000000

- ix_uer_user_score (user_id, score) was dead weight: `score` is never written, so it indexed
  all-NULL; the (user_id, entity_id) PK already serves the personalization join's WHERE user_id=.
- ix_article_entities_article (article_id) backs the now-hot feed-pool + relevance-scorer join
  (article_entities ON ca.article_id) that runs on every personalized feed/briefing/search read.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_uer_user_score", table_name="user_entity_relevance")
    op.create_index("ix_article_entities_article", "article_entities", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_article_entities_article", table_name="article_entities")
    op.create_index("ix_uer_user_score", "user_entity_relevance", ["user_id", "score"])
