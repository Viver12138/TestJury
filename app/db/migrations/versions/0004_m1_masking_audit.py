"""M1 masking audit fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_m1_masking_audit"
down_revision = "0003_m1_audit_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_runs", sa.Column("masking_policy_id", sa.Text()))
    op.add_column("model_runs", sa.Column("masking_policy_version", sa.Text()))
    op.add_column("model_runs", sa.Column("masking_report", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("model_runs", "masking_report")
    op.drop_column("model_runs", "masking_policy_version")
    op.drop_column("model_runs", "masking_policy_id")
