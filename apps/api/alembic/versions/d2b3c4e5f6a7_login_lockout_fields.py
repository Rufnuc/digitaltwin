"""login brute-force protection: user lockout fields

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-09-17 13:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2b3c4e5f6a7'
down_revision: Union[str, None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(),
                                     server_default='0', nullable=False))
    op.add_column('users', sa.Column('lockout_until', sa.DateTime(timezone=True),
                                     nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'lockout_until')
    op.drop_column('users', 'failed_login_count')
