"""M1 audit/evidence fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_m1_audit_evidence"
down_revision = "0002_m1_review_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_candidates", sa.Column("kb_grounded", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("review_candidates", sa.Column("kb_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("review_candidates", sa.Column("evidence_type", sa.Text()))
    op.add_column("review_candidates", sa.Column("evidence_strength", sa.Text()))
    op.add_column("review_candidates", sa.Column("evidence_quote", sa.Text()))
    op.add_column("review_candidates", sa.Column("model_evidence_status", sa.Text()))
    op.add_column("review_candidates", sa.Column("evidence_support_status", sa.Text()))
    op.add_column("review_candidates", sa.Column("validation_status", sa.Text(), nullable=False, server_default=sa.text("'passed'")))
    op.add_column("review_candidates", sa.Column("parse_warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("review_candidates", sa.Column("model_confidence", sa.Float()))
    op.add_column("review_candidates", sa.Column("suggestion", sa.Text()))

    op.add_column("model_runs", sa.Column("operation", sa.Text()))
    op.add_column("model_runs", sa.Column("request_hash", sa.Text()))
    op.add_column("model_runs", sa.Column("response_hash", sa.Text()))
    op.add_column("model_runs", sa.Column("error_code", sa.Text()))


def downgrade() -> None:
    op.drop_column("model_runs", "error_code")
    op.drop_column("model_runs", "response_hash")
    op.drop_column("model_runs", "request_hash")
    op.drop_column("model_runs", "operation")

    op.drop_column("review_candidates", "suggestion")
    op.drop_column("review_candidates", "model_confidence")
    op.drop_column("review_candidates", "parse_warnings")
    op.drop_column("review_candidates", "validation_status")
    op.drop_column("review_candidates", "evidence_support_status")
    op.drop_column("review_candidates", "model_evidence_status")
    op.drop_column("review_candidates", "evidence_quote")
    op.drop_column("review_candidates", "evidence_strength")
    op.drop_column("review_candidates", "evidence_type")
    op.drop_column("review_candidates", "kb_refs")
    op.drop_column("review_candidates", "kb_grounded")
