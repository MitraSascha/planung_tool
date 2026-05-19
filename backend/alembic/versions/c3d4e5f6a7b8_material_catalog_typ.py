"""material_catalog: typ-Spalte (Rohr / Ventil / Formstück / Sonstiges)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-19 11:30:00.000000

Hintergrund: Zusätzlich zur Kategorie (siehe ``b2c3d4e5f6a7``) wollen wir
**innerhalb** der Listen noch nach Material-Typ filtern können:

  * ``rohr``       — Pipes (Temponox-Rohr, etc.)
  * ``ventil``     — Strangabsperr-, Reg.-, Thermostat-Ventile
  * ``formstueck`` — Bögen, Übergangsstücke, Reduzierstücke, Muffen,
                     T-Stücke, Verschraubungen, Verschlusskappen …
  * ``sonstiges``  — Schalen, Stopfen, Stanzer (Brandschutz/Isolierung
                     fällt hauptsächlich in diese Klasse)

Die Klassifikation passiert automatisch beim Re-Import per Regex auf
``beschreibung_1`` + ``beschreibung_2`` (siehe ``services/material_catalog.py``).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "material_catalog",
        sa.Column("typ", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_material_catalog_typ", "material_catalog", ["typ"])
    # Backfill: der Backend-Startup re-importiert die CSVs ohnehin und füllt
    # das Feld dabei. Für eine sofortige Default-Belegung setzen wir alles
    # auf 'sonstiges' — wird beim ersten Re-Import sauber überschrieben.
    op.execute("UPDATE material_catalog SET typ = 'sonstiges' WHERE typ IS NULL")


def downgrade() -> None:
    op.drop_index("ix_material_catalog_typ", table_name="material_catalog")
    op.drop_column("material_catalog", "typ")
