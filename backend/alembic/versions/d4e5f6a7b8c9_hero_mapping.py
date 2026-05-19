"""users.hero_partner_id + projects.hero_project_match_id

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-19 12:30:00.000000

Hintergrund: Beim Speichern eines DailyReports soll pro Attendee eine
Tracking-Time im HERO-CRM angelegt werden (siehe
``app.services.hero.service.push_tracking_time``). Dafür brauchen wir:

  * ``users.hero_partner_id`` — die ID des Mitarbeiters in HERO
    (befüllt vom Partner-Sync, der Namen normalisiert vergleicht)
  * ``projects.hero_project_match_id`` — die HERO-ProjectMatch-ID
    (Admin setzt das manuell über die globale Suche)

Beide Felder sind nullable — fehlt eines, wird der Tracking-Time-Push
einfach übersprungen (Best-Effort).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("hero_partner_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_users_hero_partner_id", "users", ["hero_partner_id"])
    op.add_column(
        "projects",
        sa.Column("hero_project_match_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_projects_hero_project_match_id", "projects", ["hero_project_match_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_projects_hero_project_match_id", table_name="projects")
    op.drop_column("projects", "hero_project_match_id")
    op.drop_index("ix_users_hero_partner_id", table_name="users")
    op.drop_column("users", "hero_partner_id")
