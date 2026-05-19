"""daily_report_source_link: FK von MaterialIssue/Blocker auf DailyReport

Revision ID: c2f8e7a9d350
Revises: b1e5c9f4d720
Create Date: 2026-05-18 18:00:00.000000

Hintergrund: Monteure schreiben fehlendes Material und Blocker im
Freitext-Feld des Tagesberichts. Bisher landete das nicht im
Open-Points-Tracking — die Bauleitung musste den Bericht öffnen.

Neue Spalte ``source_daily_report_id`` (nullable, ondelete=SET NULL) auf
``material_issues`` und ``blockers``. Wenn der Service-Layer aus einem
Freitext einen Eintrag synchronisiert, setzt er diese FK. Damit kann
Update-Logik bestehende Auto-Sync-Zeilen wiederfinden statt zu duplizieren.

NULL = manuell angelegt (über die separaten Formulare).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f8e7a9d350"
down_revision: Union[str, None] = "b1e5c9f4d720"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("material_issues", "blockers"):
        op.add_column(
            table,
            sa.Column("source_daily_report_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_source_daily_report",
            table,
            "daily_reports",
            ["source_daily_report_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            f"ix_{table}_source_daily_report_id",
            table,
            ["source_daily_report_id"],
        )


def downgrade() -> None:
    for table in ("material_issues", "blockers"):
        op.drop_index(f"ix_{table}_source_daily_report_id", table_name=table)
        op.drop_constraint(f"fk_{table}_source_daily_report", table, type_="foreignkey")
        op.drop_column(table, "source_daily_report_id")
