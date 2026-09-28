"""purchase shipping documents + supplier-payment currency

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-09-20 09:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b6c7d8e9f0a1'
down_revision: Union[str, None] = 'a5b6c7d8e9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('supplier_payments', sa.Column('currency', sa.String(length=3),
                                                 server_default='NGN', nullable=False))
    op.create_table(
        'purchase_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=True),
        sa.Column('storage_key', sa.String(length=1024), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=32), server_default='shipping', nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_purchase_documents_purchase_id', 'purchase_documents',
                    ['purchase_id'])


def downgrade() -> None:
    op.drop_index('ix_purchase_documents_purchase_id', table_name='purchase_documents')
    op.drop_table('purchase_documents')
    op.drop_column('supplier_payments', 'currency')
