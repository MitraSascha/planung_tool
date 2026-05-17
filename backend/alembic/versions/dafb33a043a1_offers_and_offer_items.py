"""offers and offer_items

Revision ID: dafb33a043a1
Revises: d4f7b1c9e520
Create Date: 2026-05-17 07:54:10.704090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dafb33a043a1'
down_revision: Union[str, None] = 'd4f7b1c9e520'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'offers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('supplier_name', sa.String(length=255), nullable=False),
        sa.Column('offer_no', sa.String(length=128), nullable=True),
        sa.Column('offer_date', sa.Date(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('total_net_eur', sa.Float(), nullable=True),
        sa.Column('total_gross_eur', sa.Float(), nullable=True),
        sa.Column('vat_rate', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('source_type', sa.String(length=16), nullable=False),
        sa.Column('source_file', sa.String(length=512), nullable=True),
        sa.Column('attached_file_path', sa.String(length=1024), nullable=True),
        sa.Column('imported_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['imported_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_offers_project_id'), 'offers', ['project_id'], unique=False)

    op.create_table(
        'offer_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('offer_id', sa.Integer(), nullable=False),
        sa.Column('position_index', sa.Integer(), nullable=False),
        sa.Column('position_label', sa.String(length=32), nullable=True),
        sa.Column('article_no', sa.String(length=128), nullable=True),
        sa.Column('name', sa.String(length=512), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('qty', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('unit_price_net_eur', sa.Float(), nullable=True),
        sa.Column('total_net_eur', sa.Float(), nullable=True),
        sa.Column('vat_rate', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_offer_items_offer_id'), 'offer_items', ['offer_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_offer_items_offer_id'), table_name='offer_items')
    op.drop_table('offer_items')
    op.drop_index(op.f('ix_offers_project_id'), table_name='offers')
    op.drop_table('offers')
