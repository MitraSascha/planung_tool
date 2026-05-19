"""daily_reports.start_time — flexibler Schichtbeginn pro Bericht

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-19 14:30:00.000000

Schichtbeginn variiert in der Praxis (06:00 Frühschicht, 08:00 Spätstart,
Notdienst auch 22:00). Bisher war 07:00 als Default im HERO-Tracking-Push
hartkodiert — das hat User gestört. Jetzt Per-Report-Feld:

  * ``start_time`` (TIME, nullable) — falls gesetzt: wird vom Tracking-Push
    als Startzeit am ``report_date`` verwendet, end = start + ``ist_hours``.
  * Wenn ``start_time`` leer ist: greift ``settings.default_shift_start``
    (Default 07:00, in .env überschreibbar).

Backfill: nicht nötig — bestehende Reports laufen weiter mit dem
Setting-Default.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_reports",
        sa.Column("start_time", sa.Time(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_reports", "start_time")
