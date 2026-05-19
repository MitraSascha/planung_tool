"""material_usages: Verbrauchsbuchungen pro Daily-Report

Revision ID: d3f6a9b2c715
Revises: c2e5f8a3b412
Create Date: 2026-05-18 06:50:00.000000

Neue Tabelle `material_usages`: Jeder Eintrag dokumentiert, wieviel von
einem Material an einem Tag (optional verknüpft mit einem Daily-Report)
verbaut wurde. Die `material_items.ist_qty`-Spalte wird applikationsseitig
als Summe aller usages eines Items gepflegt.

FK-Verhalten:
- project_id: CASCADE (Buchungen sind eigentum des Projekts)
- material_item_id: SET NULL (Buchung bleibt als historisches Audit-Event
  bestehen, auch wenn der Material-Stamm gelöscht wird)
- daily_report_id: SET NULL (analog — Bericht-Löschung soll Buchungen
  nicht verlieren)
- user_id: SET NULL
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3f6a9b2c715"
down_revision: Union[str, None] = "c2e5f8a3b412"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_usages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_item_id",
            sa.Integer(),
            sa.ForeignKey("material_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "daily_report_id",
            sa.Integer(),
            sa.ForeignKey("daily_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("section_number", sa.Integer(), nullable=True),
        sa.Column("qty_used", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("used_at", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_material_usages_project_id", "material_usages", ["project_id"]
    )
    op.create_index(
        "ix_material_usages_material_item_id",
        "material_usages",
        ["material_item_id"],
    )
    op.create_index(
        "ix_material_usages_daily_report_id",
        "material_usages",
        ["daily_report_id"],
    )
    op.create_index(
        "ix_material_usages_used_at", "material_usages", ["used_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_material_usages_used_at", table_name="material_usages")
    op.drop_index(
        "ix_material_usages_daily_report_id", table_name="material_usages"
    )
    op.drop_index(
        "ix_material_usages_material_item_id", table_name="material_usages"
    )
    op.drop_index(
        "ix_material_usages_project_id", table_name="material_usages"
    )
    op.drop_table("material_usages")
