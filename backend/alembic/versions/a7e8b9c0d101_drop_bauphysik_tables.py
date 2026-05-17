"""drop bauphysik tables (feature removed)

Revision ID: a7e8b9c0d101
Revises: 3d99d2552945
Create Date: 2026-05-17 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7e8b9c0d101'
down_revision: Union[str, None] = '3d99d2552945'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_building_components_room_id', table_name='building_components')
    op.drop_table('building_components')
    op.drop_index('ix_building_rooms_project_id', table_name='building_rooms')
    op.drop_table('building_rooms')


def downgrade() -> None:
    # Bauphysik feature was removed — re-create the tables minimally to support a
    # downgrade path. Schema matches the original 1fb51b8ce7d5 migration.
    import sqlalchemy as sa

    op.create_table(
        'building_rooms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('position_index', sa.Integer(), nullable=False),
        sa.Column('wohneinheit', sa.String(length=128), nullable=True),
        sa.Column('floor', sa.String(length=32), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('area_sqm', sa.Float(), nullable=True),
        sa.Column('height_m', sa.Float(), nullable=True),
        sa.Column('room_temp_c', sa.Float(), nullable=True),
        sa.Column('air_change_rate', sa.Float(), nullable=True),
        sa.Column('transmission_loss_w', sa.Float(), nullable=True),
        sa.Column('ventilation_loss_w', sa.Float(), nullable=True),
        sa.Column('total_heat_load_w', sa.Float(), nullable=True),
        sa.Column('source_sheet', sa.String(length=64), nullable=True),
        sa.Column('source_file', sa.String(length=512), nullable=True),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_building_rooms_project_id', 'building_rooms', ['project_id'], unique=False)
    op.create_table(
        'building_components',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('position_index', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('type_desc', sa.String(length=255), nullable=True),
        sa.Column('u_value', sa.Float(), nullable=True),
        sa.Column('z_value', sa.Float(), nullable=True),
        sa.Column('length_m', sa.Float(), nullable=True),
        sa.Column('height_or_width_m', sa.Float(), nullable=True),
        sa.Column('area_sqm', sa.Float(), nullable=True),
        sa.Column('t_room_c', sa.Float(), nullable=True),
        sa.Column('t_adjacent_c', sa.Float(), nullable=True),
        sa.Column('fx', sa.Float(), nullable=True),
        sa.Column('delta_t_k', sa.Float(), nullable=True),
        sa.Column('heat_load_w', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['building_rooms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_building_components_room_id', 'building_components', ['room_id'], unique=False)
