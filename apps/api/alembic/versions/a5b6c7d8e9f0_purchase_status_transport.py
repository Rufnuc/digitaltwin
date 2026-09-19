"""purchase procurement: status + transport_cost

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-09-19 13:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchases', sa.Column('transport_cost', sa.Numeric(14, 2),
                                         server_default='0', nullable=False))
    # Any existing purchase is a historical actual → RECEIVED; new ones default REQUEST.
    op.add_column('purchases', sa.Column('status', sa.String(length=16),
                                         server_default='RECEIVED', nullable=False))
    op.create_index('ix_purchases_status', 'purchases', ['status'])


def downgrade() -> None:
    op.drop_index('ix_purchases_status', table_name='purchases')
    op.drop_column('purchases', 'status')
    op.drop_column('purchases', 'transport_cost')
