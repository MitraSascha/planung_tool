"""daily_report_attendees: strukturierte Team-Anwesenheit pro Tagesbericht

Revision ID: f7d2c891b340
Revises: e5c1b3d8a920
Create Date: 2026-05-18 08:30:00.000000

Bisher war ``daily_reports.team`` ein Freitext (z.B. "Rojhat, Murat,
Igor"), aus dem sich Team-KPIs nur ungenau ableiten ließen. Neue
many-to-many-Tabelle ``daily_report_attendees`` (daily_report × user)
ermöglicht strukturierte Auswertung wie "wer war an welchen Tagen
gelb/rot" oder "wieviele Tage hat Murat gearbeitet".

Freitext-Feld bleibt als Fallback bestehen.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7d2c891b340"
down_revision: Union[str, None] = "e5c1b3d8a920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_report_attendees",
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("daily_report_id", "user_id", name="uq_daily_attendee"),
    )
    op.create_index(
        "ix_daily_report_attendees_report",
        "daily_report_attendees",
        ["daily_report_id"],
    )
    op.create_index(
        "ix_daily_report_attendees_user",
        "daily_report_attendees",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_report_attendees_user", table_name="daily_report_attendees")
    op.drop_index("ix_daily_report_attendees_report", table_name="daily_report_attendees")
    op.drop_table("daily_report_attendees")
