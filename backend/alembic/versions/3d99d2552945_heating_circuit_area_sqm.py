"""heating_circuit area_sqm

Revision ID: 3d99d2552945
Revises: 1fb51b8ce7d5
Create Date: 2026-05-17 09:06:05.876888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d99d2552945'
down_revision: Union[str, None] = '1fb51b8ce7d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('heating_circuits', sa.Column('area_sqm', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('heating_circuits', 'area_sqm')
