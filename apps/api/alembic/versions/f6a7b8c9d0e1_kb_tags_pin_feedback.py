"""Knowledgebase: tags, pinned, helpful counts + feedback table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-02 15:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kb_articles", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("kb_articles", sa.Column("pinned", sa.Boolean(), nullable=False,
                                           server_default=sa.false()))
    op.add_column("kb_articles", sa.Column("helpful_yes", sa.Integer(), nullable=False,
                                           server_default="0"))
    op.add_column("kb_articles", sa.Column("helpful_no", sa.Integer(), nullable=False,
                                           server_default="0"))
    op.create_index("ix_kb_articles_pinned", "kb_articles", ["pinned"])

    op.create_table(
        "kb_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(),
                  sa.ForeignKey("kb_articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.UniqueConstraint("article_id", "user_id", name="uq_kb_feedback_user"),
    )
    op.create_index("ix_kb_feedback_article_id", "kb_feedback", ["article_id"])
    op.create_index("ix_kb_feedback_user_id", "kb_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_table("kb_feedback")
    op.drop_index("ix_kb_articles_pinned", table_name="kb_articles")
    op.drop_column("kb_articles", "helpful_no")
    op.drop_column("kb_articles", "helpful_yes")
    op.drop_column("kb_articles", "pinned")
    op.drop_column("kb_articles", "tags")
