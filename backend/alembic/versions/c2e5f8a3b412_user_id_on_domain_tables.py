"""user_id on material_items and risk_issues

Revision ID: c2e5f8a3b412
Revises: c1d4e7f9a201
Create Date: 2026-05-17 16:10:00.000000

`MaterialIssue` and `Blocker` already track which user filed them.
`MaterialItem` and `RiskIssue` did not — closes that audit gap.
Nullable so the existing rows survive.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2e5f8a3b412"
down_revision: Union[str, None] = "c1d4e7f9a201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "material_items",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "risk_issues",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_issues", "user_id")
    op.drop_column("material_items", "user_id")
