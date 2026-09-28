"""purchase_documents: optional payment_id (receipts tied to a payment)

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-09-21 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'b6c7d8e9f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_documents',
                  sa.Column('payment_id', sa.Integer(), nullable=True))
    op.create_index('ix_purchase_documents_payment_id', 'purchase_documents',
                    ['payment_id'])
    op.create_foreign_key('fk_purchase_documents_payment', 'purchase_documents',
                          'supplier_payments', ['payment_id'], ['id'],
                          ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint('fk_purchase_documents_payment', 'purchase_documents',
                       type_='foreignkey')
    op.drop_index('ix_purchase_documents_payment_id', table_name='purchase_documents')
    op.drop_column('purchase_documents', 'payment_id')
