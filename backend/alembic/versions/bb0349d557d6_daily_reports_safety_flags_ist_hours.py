"""daily_reports safety flags + ist_hours

Revision ID: bb0349d557d6
Revises: a9894a224556
Create Date: 2026-05-17 12:31:47.424426

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb0349d557d6'
down_revision: Union[str, None] = 'a9894a224556'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('daily_reports', sa.Column('safety_psa', sa.Boolean(), nullable=True))
    op.add_column('daily_reports', sa.Column('safety_tools', sa.Boolean(), nullable=True))
    op.add_column('daily_reports', sa.Column('safety_material', sa.Boolean(), nullable=True))
    op.add_column('daily_reports', sa.Column('safety_workarea', sa.Boolean(), nullable=True))
    op.add_column('daily_reports', sa.Column('safety_approval', sa.Boolean(), nullable=True))
    op.add_column('daily_reports', sa.Column('ist_hours', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('daily_reports', 'ist_hours')
    op.drop_column('daily_reports', 'safety_approval')
    op.drop_column('daily_reports', 'safety_workarea')
    op.drop_column('daily_reports', 'safety_material')
    op.drop_column('daily_reports', 'safety_tools')
    op.drop_column('daily_reports', 'safety_psa')
