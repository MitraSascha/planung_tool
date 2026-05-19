"""material_items.offer_item_id: FK auf offer_items

Revision ID: e5c1b3d8a920
Revises: d3f6a9b2c715
Create Date: 2026-05-18 08:00:00.000000

Material-Stamm wird zukünftig beim Offer-Upload automatisch aus den
offer_items kopiert. Damit wir später bei Offer-Updates dedupen können
und im Material-Sheet pro Stamm-Position auf die Quell-Angebot-Position
verweisen können, bekommen material_items eine optionale FK auf
offer_items.

FK-Verhalten: ON DELETE SET NULL — wenn ein Angebot gelöscht wird,
bleibt das Material-Item bestehen (es kann ja schon verbaut sein),
verliert nur den Rückverweis.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5c1b3d8a920"
down_revision: Union[str, None] = "d3f6a9b2c715"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "material_items",
        sa.Column(
            "offer_item_id",
            sa.Integer(),
            sa.ForeignKey("offer_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_material_items_offer_item_id",
        "material_items",
        ["offer_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_material_items_offer_item_id", table_name="material_items")
    op.drop_column("material_items", "offer_item_id")
