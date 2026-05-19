"""daily_reports: raw_work_log + raw_work_log_language Spalten

Revision ID: f4a9c2e8b513
Revises: e3b1f5a7c290
Create Date: 2026-05-19 06:00:00.000000

Hintergrund: Bisher hatte der Tagesbericht zwei separate Felder
``completed_work`` und ``open_work``. Beim neuen „Arbeitstagerfassung"-Flow
gibt der Monteur **einen** Roh-Text ein (Text oder Voice), den ein LLM
in Erledigt/Offen splittet. Dieser Roh-Text bleibt persistent unter
``raw_work_log``, damit:

  * der Split beim Edit reproduzierbar ist (Quelle bleibt unverändert),
  * der Originaltext (z.B. nicht-deutsche Voice-Aufnahme aus Whisper) für
    Audit/Manuelle Korrektur erhalten bleibt.

``raw_work_log_language`` (ISO 639-1) speichert die von Whisper erkannte
Sprache der Aufnahme. So sieht die Bauleitung später ob die Übersetzungs-
Pipeline aktiv war.

Backfill: nicht nötig — bestehende DailyReports haben ``completed_work``/
``open_work`` separat erfasst (Wizard schreibt beide direkt). Neue Reports
nutzen die Arbeitstagerfassung. Beide Wege bleiben für eine Weile
nebeneinander zulässig.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f4a9c2e8b513"
down_revision: Union[str, None] = "e3b1f5a7c290"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_reports",
        sa.Column("raw_work_log", sa.Text(), nullable=True),
    )
    op.add_column(
        "daily_reports",
        sa.Column("raw_work_log_language", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_reports", "raw_work_log_language")
    op.drop_column("daily_reports", "raw_work_log")
