"""project client_name field

Revision ID: a9894a224556
Revises: a7e8b9c0d101
Create Date: 2026-05-17 11:57:49.918536

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9894a224556'
down_revision: Union[str, None] = 'a7e8b9c0d101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('client_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'client_name')
