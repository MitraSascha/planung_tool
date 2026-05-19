"""daily_report_hero_pushes: Audit-Tabelle für HERO-Tracking-Time-Pushes

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-19 13:30:00.000000

Pro DailyReport × Attendee wird einmalig eine HERO-Tracking-Time angelegt
(siehe ``app.services.hero.tracking_push``). Wir merken uns die
HERO-IDs lokal, damit beim DailyReport-Edit kein zweites Mal gepusht,
sondern die existierende HERO-Zeile **updated** wird (HERO unterstützt
``update_tracking_time(id=...)`` für genau diesen Zweck).

Felder:
  * ``hero_tracking_time_id`` — HERO-Side ID (gesetzt nach erfolgreichem Push)
  * ``hero_tracking_time_uuid`` — optional zur Side-Verification
  * ``pushed_at`` — letzter erfolgreicher Push
  * ``last_error`` — letzter Fehler-Text (für Diagnose)
  * ``last_attempt_at`` — Zeitpunkt des letzten Versuchs (auch fehlgeschlagen)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_report_hero_pushes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "daily_report_id",
            sa.Integer(),
            sa.ForeignKey("daily_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hero_tracking_time_id", sa.Integer(), nullable=True),
        sa.Column("hero_tracking_time_uuid", sa.String(length=64), nullable=True),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "daily_report_id", "user_id", name="uq_drhp_report_user"
        ),
    )
    op.create_index(
        "ix_drhp_daily_report_id", "daily_report_hero_pushes", ["daily_report_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_drhp_daily_report_id", table_name="daily_report_hero_pushes")
    op.drop_table("daily_report_hero_pushes")
