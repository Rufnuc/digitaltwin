"""Knowledgebase: internal (developer-only) flag on articles

Revision ID: a7b8c9d0e1f3
Revises: f6a7b8c9d0e1
Create Date: 2026-10-02 16:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f3"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kb_articles", sa.Column("internal", sa.Boolean(), nullable=False,
                                           server_default=sa.false()))
    op.create_index("ix_kb_articles_internal", "kb_articles", ["internal"])


def downgrade() -> None:
    op.drop_index("ix_kb_articles_internal", table_name="kb_articles")
    op.drop_column("kb_articles", "internal")
