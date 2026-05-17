"""document_templates table

Stores Jinja2 templates used to render project documents from the domain
data (sections, staff, blockers, …) — replaces the per-run generated HTML
files under storage/projects/<slug>/.

Revision ID: b7e2f9c4a1d0
Revises: a3c1f0d4b7e8
Create Date: 2026-05-16 21:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e2f9c4a1d0"
down_revision: Union[str, None] = "a3c1f0d4b7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("html_template", sa.Text(), nullable=False),
        sa.Column("data_schema", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
        sa.UniqueConstraint("slug", name="uq_document_template_slug"),
    )
    op.create_index(
        "ix_document_templates_slug", "document_templates", ["slug"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_templates_slug", table_name="document_templates")
    op.drop_table("document_templates")
