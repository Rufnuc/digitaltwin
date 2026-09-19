"""waybill fields: apprentice + transport company + station

Revision ID: f4a5b6c7d8e9
Revises: e3c4d5f6a7b8
Create Date: 2026-09-19 12:00:00.000000

Matches the real dispatch flow: an apprentice carries goods to a park/station, then
a transport company/vehicle takes them onward (the driver's name isn't known, so we
keep the company + phone). Renames driver_name -> transport_company and adds
apprentice_name + station.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e3c4d5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('waybills', sa.Column('apprentice_name', sa.String(length=128), nullable=True))
    op.add_column('waybills', sa.Column('station', sa.String(length=128), nullable=True))
    op.alter_column('waybills', 'driver_name', new_column_name='transport_company')


def downgrade() -> None:
    op.alter_column('waybills', 'transport_company', new_column_name='driver_name')
    op.drop_column('waybills', 'station')
    op.drop_column('waybills', 'apprentice_name')
