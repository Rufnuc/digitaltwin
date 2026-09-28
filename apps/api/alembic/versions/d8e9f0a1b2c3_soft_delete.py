"""app-wide soft delete: deleted_at on core business entities

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-09-21 11:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ["customers", "suppliers", "products", "expenses",
           "warehouses", "branches", "employees"]


def upgrade() -> None:
    for t in _TABLES:
        op.add_column(t, sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        op.create_index(f'ix_{t}_deleted_at', t, ['deleted_at'])


def downgrade() -> None:
    for t in _TABLES:
        op.drop_index(f'ix_{t}_deleted_at', table_name=t)
        op.drop_column(t, 'deleted_at')
