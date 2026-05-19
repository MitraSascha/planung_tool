"""material_catalog: kategorie-Spalte (Standard / Brandschutz / Isolierung)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-19 10:00:00.000000

Hintergrund: Der Chef pflegt drei separate Materiallisten als CSV im
Repo-Root:

  * ``Materialliste.csv``           → Standard (Heizkörper, Temponox, Heimeier, …)
  * ``Material Brandschutz.csv``    → Brandschutz (Conlit-Schalen, Deckenstanzer)
  * ``Materialliste Isolierung.csv`` → Isolierung (Rohrschalen GEG)

Alle drei landen in derselben Tabelle, unterscheidbar über ``kategorie``.
Der Picker im Tagesbericht zeigt Filter-Chips. ``NULL`` ist erlaubt für
Altbestand (vor dieser Migration importierte Zeilen), wird aber beim
nächsten Re-Import befüllt.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "material_catalog",
        sa.Column("kategorie", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_material_catalog_kategorie",
        "material_catalog",
        ["kategorie"],
    )
    # Bestehende Zeilen (vom ersten Import) sind alle aus der Standard-Liste —
    # wir setzen sie initial auf 'standard', damit Filter-Chips sofort sinnvoll
    # funktionieren. Re-Import überschreibt das ggf. wenn die CSV-Mappings
    # sich ändern.
    op.execute("UPDATE material_catalog SET kategorie = 'standard' WHERE kategorie IS NULL")


def downgrade() -> None:
    op.drop_index("ix_material_catalog_kategorie", table_name="material_catalog")
    op.drop_column("material_catalog", "kategorie")
