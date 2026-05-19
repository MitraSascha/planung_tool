"""material_items: source-Spalte + Artikelstamm-Referenz für Nachkalkulation

Revision ID: d9a3b4c8e162
Revises: c2f8e7a9d350
Create Date: 2026-05-18 19:00:00.000000

Hintergrund: Der Monteur kann nun beim Tagesbericht-Materialdialog ad-hoc
Material aus der externen Artikelstamm-DB (>2 Mio DATANORM-Artikel)
nachladen, wenn das benötigte Teil nicht im Projekt-Angebot enthalten war.
Damit später eine Nachkalkulation („was wurde zusätzlich zum Angebot
verbaut?") und das Schreiben von Nachträgen möglich ist, brauchen die
MaterialItems eine explizite Herkunfts-Spalte:

  * ``source = 'offer'``      → aus einem Angebot übernommen (offer_item_id gesetzt)
  * ``source = 'manual'``     → von Hand angelegt (Werkzeug, Initial-Inventar)
  * ``source = 'artikelstamm'`` → ad-hoc-Kauf, Großhändlerartikel via Artikelstamm-DB
  * ``source = 'daily_report_freitext'`` → künftig: aus Daily-Report-Material-Feldern

Zusätzlich speichern wir die Artikelstamm-Artikelnummer und den Listenpreis
zum Zeitpunkt des Anlegens, damit die Nachkalkulation die Werte direkt
nutzen kann ohne erneut in der externen DB nachzuschlagen.

Backfill: bestehende Zeilen mit offer_item_id → 'offer', sonst → 'manual'.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d9a3b4c8e162"
down_revision: Union[str, None] = "c2f8e7a9d350"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "material_items",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.add_column(
        "material_items",
        sa.Column("artikelstamm_artikelnummer", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "material_items",
        sa.Column("artikelstamm_preis_eur", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_material_items_source", "material_items", ["source"]
    )
    op.create_index(
        "ix_material_items_artikelstamm_artikelnummer",
        "material_items",
        ["artikelstamm_artikelnummer"],
    )
    # Backfill: Items mit offer_item_id → 'offer'
    op.execute(
        "UPDATE material_items SET source = 'offer' WHERE offer_item_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_material_items_artikelstamm_artikelnummer", table_name="material_items")
    op.drop_index("ix_material_items_source", table_name="material_items")
    op.drop_column("material_items", "artikelstamm_preis_eur")
    op.drop_column("material_items", "artikelstamm_artikelnummer")
    op.drop_column("material_items", "source")
