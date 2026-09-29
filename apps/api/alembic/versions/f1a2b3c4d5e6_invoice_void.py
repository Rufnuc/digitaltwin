"""invoice void (voided_at, voided_by, reason)

Revision ID: f1a2b3c4d5e6
Revises: e9f0a1b2c3d4
Create Date: 2026-09-29 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("voided_by_user_id", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("void_reason", sa.String(length=255), nullable=True))
    op.create_index("ix_invoices_voided_at", "invoices", ["voided_at"])


def downgrade() -> None:
    op.drop_index("ix_invoices_voided_at", table_name="invoices")
    op.drop_column("invoices", "void_reason")
    op.drop_column("invoices", "voided_by_user_id")
    op.drop_column("invoices", "voided_at")
