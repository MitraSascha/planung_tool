"""form_responses table

Stores per-user per-field answers entered into generated HTML documents.
The (project, document_path, field_id, filled_by_user_id) tuple is unique
so each user has at most one answer per field; project leads aggregate
across users in the read path.

Revision ID: a3c1f0d4b7e8
Revises: 22217dc1505e
Create Date: 2026-05-16 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c1f0d4b7e8"
down_revision: Union[str, None] = "22217dc1505e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "form_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_path", sa.String(length=512), nullable=False),
        sa.Column("field_id", sa.String(length=255), nullable=False),
        # value_type tags which of the value_* columns is authoritative.
        # Storing per-type columns keeps queries cheap (e.g. "all true
        # checkboxes for project X") without parsing JSON.
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        sa.Column("value_number", sa.Float(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column(
            "filled_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "filled_at",
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
        sa.UniqueConstraint(
            "project_id",
            "document_path",
            "field_id",
            "filled_by_user_id",
            name="uq_form_response_user_doc_field",
        ),
    )
    op.create_index(
        "ix_form_responses_project_doc",
        "form_responses",
        ["project_id", "document_path"],
    )
    op.create_index(
        "ix_form_responses_project_user",
        "form_responses",
        ["project_id", "filled_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_form_responses_project_user", table_name="form_responses")
    op.drop_index("ix_form_responses_project_doc", table_name="form_responses")
    op.drop_table("form_responses")
