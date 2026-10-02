"""POS reconciliation: expected_pos_payments + pos_transactions

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-10-02 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expected_pos_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(),
                  sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("terminal_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("provider_request_id", sa.String(128), nullable=True),
        sa.Column("pushed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pos_transaction_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_expected_pos_payments_invoice_id", "expected_pos_payments", ["invoice_id"])
    op.create_index("ix_expected_pos_payments_terminal_id", "expected_pos_payments", ["terminal_id"])
    op.create_index("ix_expected_pos_payments_status", "expected_pos_payments", ["status"])
    op.create_index("ix_expected_pos_payments_expires_at", "expected_pos_payments", ["expires_at"])

    op.create_table(
        "pos_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_txn_id", sa.String(128), nullable=False),
        sa.Column("terminal_id", sa.String(64), nullable=True),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("reference", sa.String(128), nullable=True),
        sa.Column("masked_pan", sa.String(32), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="UNMATCHED"),
        sa.Column("invoice_id", sa.Integer(),
                  sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("expected_payment_id", sa.Integer(), nullable=True),
        sa.Column("matched_by_user_id", sa.Integer(), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("match_method", sa.String(24), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_txn_id", name="uq_pos_txn_provider_id"),
    )
    op.create_index("ix_pos_transactions_provider", "pos_transactions", ["provider"])
    op.create_index("ix_pos_transactions_provider_txn_id", "pos_transactions", ["provider_txn_id"])
    op.create_index("ix_pos_transactions_terminal_id", "pos_transactions", ["terminal_id"])
    op.create_index("ix_pos_transactions_status", "pos_transactions", ["status"])
    op.create_index("ix_pos_transactions_invoice_id", "pos_transactions", ["invoice_id"])
    op.create_index("ix_pos_transactions_occurred_at", "pos_transactions", ["occurred_at"])
    op.create_index("ix_pos_transactions_received_at", "pos_transactions", ["received_at"])


def downgrade() -> None:
    op.drop_table("pos_transactions")
    op.drop_table("expected_pos_payments")
