"""milestones: abgeleitete Projekt-Meilensteine

Revision ID: a8e4b2f1c635
Revises: f7d2c891b340
Create Date: 2026-05-18 09:30:00.000000

Tabelle ``milestones`` für die zentral verwaltete Liste der
Projekt-Meilensteine. Drei Typen werden automatisch befüllt
(siehe services/milestones.py):

- ``section_end``     : pro Bauabschnitt ein Meilenstein am geplanten
                        Abschnittsende.
- ``druckpruefung``   : pro Abschnitt einer, getriggert wenn in der
                        Checkliste "Prüfprotokoll erstellt" gehakt wird.
- ``inbetriebnahme``  : einmalig pro Projekt, getriggert wenn das
                        Inbetriebnahmeprotokoll generiert/freigegeben wird.

Manuelle Meilensteine sind ebenfalls möglich (type='custom').
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8e4b2f1c635"
down_revision: Union[str, None] = "f7d2c891b340"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "milestones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(32), nullable=False),
        # type: 'section_end' | 'druckpruefung' | 'inbetriebnahme' | 'custom'
        sa.Column(
            "section_id",
            sa.Integer(),
            sa.ForeignKey("project_sections.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("actual_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        # status: 'pending' | 'done' | 'overdue' (overdue wird live berechnet)
        sa.Column(
            "auto_generated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "type",
            "section_id",
            name="uq_milestone_proj_type_section",
        ),
    )
    op.create_index("ix_milestones_project_id", "milestones", ["project_id"])
    op.create_index("ix_milestones_type", "milestones", ["type"])


def downgrade() -> None:
    op.drop_index("ix_milestones_type", table_name="milestones")
    op.drop_index("ix_milestones_project_id", table_name="milestones")
    op.drop_table("milestones")
