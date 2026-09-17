"""hardening: unique invoice number + idempotency keys

Revision ID: c1a2b3d4e5f6
Revises: 869fec8c9d0a
Create Date: 2026-09-17 12:00:00.000000

Manual precondition: `invoice_number` must already be unique in the data before the
unique constraint is created. Checked at audit time (0 duplicates found). If any
exist later, resolve them first — this migration will fail rather than guess.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = '869fec8c9d0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotency keys for money/stock-moving writes (sale, invoice, payment).
    op.create_table(
        'idempotency_keys',
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('scope', sa.String(length=64), nullable=False),
        sa.Column('response_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    # Business-key uniqueness for invoice numbers (a duplicate is a double-write).
    op.create_unique_constraint('uq_invoices_invoice_number', 'invoices', ['invoice_number'])


def downgrade() -> None:
    op.drop_constraint('uq_invoices_invoice_number', 'invoices', type_='unique')
    op.drop_table('idempotency_keys')
