"""Four new domain tables: section_schedules, team_status, material_items, risk_issues.

These replace the hard-coded lists in the six bauleitung/obermonteur templates
that the user had open structural questions about. Once populated, their data
propagates into Gantt, Wochenplan, Meilensteinplan, Statusübersicht etc.
automatically via the renderer context.

Revision ID: a4b8d2f5e310
Revises: f3a8c2e6d109
Create Date: 2026-05-17 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4b8d2f5e310"
down_revision: Union[str, None] = "f3a8c2e6d109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "section_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("project_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("section_id", name="uq_section_schedule_section"),
    )

    op.create_table(
        "team_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="green"),
        sa.Column("soll_hours", sa.Float(), nullable=True),
        sa.Column("ist_hours", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "user_id", "day", name="uq_team_status_per_day"),
    )
    op.create_index("ix_team_status_project_id", "team_status", ["project_id"])
    op.create_index("ix_team_status_day", "team_status", ["day"])

    op.create_table(
        "material_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_number", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="material"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("soll_qty", sa.Float(), nullable=True),
        sa.Column("ist_qty", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="vorhanden"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_material_items_project_id", "material_items", ["project_id"])

    op.create_table(
        "risk_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_number", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="risiko"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="mittel"),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="offen"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_risk_issues_project_id", "risk_issues", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_issues_project_id", table_name="risk_issues")
    op.drop_table("risk_issues")
    op.drop_index("ix_material_items_project_id", table_name="material_items")
    op.drop_table("material_items")
    op.drop_index("ix_team_status_day", table_name="team_status")
    op.drop_index("ix_team_status_project_id", table_name="team_status")
    op.drop_table("team_status")
    op.drop_table("section_schedules")
