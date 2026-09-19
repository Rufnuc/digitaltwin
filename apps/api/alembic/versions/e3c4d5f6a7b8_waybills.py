"""waybills: dispatch records linked to invoices

Revision ID: e3c4d5f6a7b8
Revises: d2b3c4e5f6a7
Create Date: 2026-09-19 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e3c4d5f6a7b8'
down_revision: Union[str, None] = 'd2b3c4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'waybills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('waybill_number', sa.String(length=64), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='PENDING'),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('driver_name', sa.String(length=128), nullable=True),
        sa.Column('driver_phone', sa.String(length=32), nullable=True),
        sa.Column('vehicle_info', sa.String(length=128), nullable=True),
        sa.Column('receiver_name', sa.String(length=128), nullable=True),
        sa.Column('receiver_phone', sa.String(length=32), nullable=True),
        sa.Column('destination', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('waybill_number'),
    )
    op.create_index('ix_waybills_invoice_id', 'waybills', ['invoice_id'])
    op.create_index('ix_waybills_status', 'waybills', ['status'])
    op.create_index('ix_waybills_waybill_number', 'waybills', ['waybill_number'])


def downgrade() -> None:
    op.drop_index('ix_waybills_waybill_number', table_name='waybills')
    op.drop_index('ix_waybills_status', table_name='waybills')
    op.drop_index('ix_waybills_invoice_id', table_name='waybills')
    op.drop_table('waybills')
