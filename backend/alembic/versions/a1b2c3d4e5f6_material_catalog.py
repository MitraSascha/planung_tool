"""material_catalog: kuratierte Artikel-Liste für die Materialerfassung

Revision ID: a1b2c3d4e5f6
Revises: f4a9c2e8b513
Create Date: 2026-05-19 09:00:00.000000

Hintergrund: Der Monteur soll im Tagesbericht „fehlendes Material" aus einer
**kuratierten Liste** (vom Chef gepflegt, ~170 Artikel) auswählen statt frei
einzutippen. Damit landen einheitliche Bezeichnungen in den
Materialmeldungen — wichtig für Bestellungen + Nachkalkulation.

Tabellenfelder:

* ``artikelnummer`` — Primärer Identifier in der Liste (eindeutig, z.B.
  ``SPRIND54``, ``TEMPB1545``). Wird in den Materialmeldungen als
  ``MaterialIssue.description`` mit-geschrieben.
* ``beschreibung_1`` — Haupt-Bezeichnung (z.B. „Temponox Bogen 90 Grad, 15mm").
* ``beschreibung_2`` — Zusatz (Maße, Material, Hinweise).
* ``listenpreis_eur`` / ``nettowert_eur`` — beide aus der CSV; Listenpreis ist
  der Brutto-Listenpreis, Nettowert oft mit Rabatt. Beide aufbewahren, damit
  spätere Auswertungen entscheiden können.
* ``einheit`` — derzeit nicht in der CSV separat, kann später ergänzt werden
  (NULL erlaubt).
* ``sort_key`` — vorberechnete Sortier-Reihenfolge (Beschreibung 1 +
  Beschreibung 2 lowercased), damit der Dropdown server-seitig sortiert
  ausliefern kann ohne Locale-Kollation.
* ``active`` — wird beim Re-Import auf ``True`` gesetzt; Artikel, die in der
  neuen CSV fehlen, werden auf ``False`` gesetzt statt gelöscht (Audit-Trail).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f4a9c2e8b513"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_catalog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artikelnummer", sa.String(length=32), nullable=False),
        sa.Column("beschreibung_1", sa.String(length=255), nullable=False),
        sa.Column("beschreibung_2", sa.String(length=255), nullable=True),
        sa.Column("listenpreis_eur", sa.Float(), nullable=True),
        sa.Column("nettowert_eur", sa.Float(), nullable=True),
        sa.Column("einheit", sa.String(length=16), nullable=True),
        sa.Column("sort_key", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("artikelnummer", name="uq_material_catalog_artikelnummer"),
    )
    op.create_index(
        "ix_material_catalog_active_sort",
        "material_catalog",
        ["active", "sort_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_material_catalog_active_sort", table_name="material_catalog")
    op.drop_table("material_catalog")
