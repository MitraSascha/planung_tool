"""material_issues: Beschaffungs-Workflow (Stepper Offen -> Bestellt -> Unterwegs -> Angekommen)

Revision ID: e3b1f5a7c290
Revises: d9a3b4c8e162
Create Date: 2026-05-18 21:00:00.000000

Hintergrund: Bisher hatten Materialmeldungen nur ein einfaches
``status``-Feld (``open`` / ``in_progress`` / ``done``). Für die
Bauleitung ist das zu grob: sie will sehen, ob ein gemeldeter
Materialbedarf bereits *bestellt* wurde, noch *unterwegs* (Lieferung)
ist oder bereits auf der Baustelle *angekommen* ist. Pro Stufe wird
ein Audit (Timestamp + auslösender User) festgehalten, damit später
Rückfragen ("wer hat das wann bestellt?") beantwortet werden können.

Neues Feld:

  * ``procurement_status``: ``offen`` | ``bestellt`` | ``unterwegs`` | ``angekommen``
  * pro Stufe ``*_at`` + ``*_by_user_id`` (Audit-Trail)

Backfill: bestehende Zeilen mit ``status='done'`` werden auf
``procurement_status='angekommen'`` gesetzt und bekommen ``arrived_at=now()``
gestempelt (kein Audit-User, weil retroaktiv). Alle anderen Zeilen
bleiben auf dem Default ``'offen'``.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e3b1f5a7c290"
down_revision: Union[str, None] = "d9a3b4c8e162"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "material_issues",
        sa.Column(
            "procurement_status",
            sa.String(length=16),
            nullable=False,
            server_default="offen",
        ),
    )
    op.add_column(
        "material_issues",
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "material_issues",
        sa.Column("ordered_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "material_issues",
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "material_issues",
        sa.Column("shipped_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "material_issues",
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "material_issues",
        sa.Column("arrived_by_user_id", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_material_issues_ordered_by_user",
        "material_issues",
        "users",
        ["ordered_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_material_issues_shipped_by_user",
        "material_issues",
        "users",
        ["shipped_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_material_issues_arrived_by_user",
        "material_issues",
        "users",
        ["arrived_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_material_issues_procurement_status",
        "material_issues",
        ["procurement_status"],
    )

    # Backfill: 'done' -> angekommen + arrived_at=now() (kein User-Stempel,
    # weil retroaktiv).
    op.execute(
        "UPDATE material_issues "
        "SET procurement_status = 'angekommen', arrived_at = now() "
        "WHERE status = 'done'"
    )


def downgrade() -> None:
    op.drop_index("ix_material_issues_procurement_status", table_name="material_issues")
    op.drop_constraint(
        "fk_material_issues_arrived_by_user", "material_issues", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_material_issues_shipped_by_user", "material_issues", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_material_issues_ordered_by_user", "material_issues", type_="foreignkey"
    )
    op.drop_column("material_issues", "arrived_by_user_id")
    op.drop_column("material_issues", "arrived_at")
    op.drop_column("material_issues", "shipped_by_user_id")
    op.drop_column("material_issues", "shipped_at")
    op.drop_column("material_issues", "ordered_by_user_id")
    op.drop_column("material_issues", "ordered_at")
    op.drop_column("material_issues", "procurement_status")
