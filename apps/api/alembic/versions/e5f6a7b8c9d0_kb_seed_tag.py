"""Knowledgebase: add seed_tag to kb_articles

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-02 14:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kb_articles", sa.Column("seed_tag", sa.String(32), nullable=True))
    op.create_index("ix_kb_articles_seed_tag", "kb_articles", ["seed_tag"])


def downgrade() -> None:
    op.drop_index("ix_kb_articles_seed_tag", table_name="kb_articles")
    op.drop_column("kb_articles", "seed_tag")
