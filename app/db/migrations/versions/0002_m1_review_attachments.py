"""M1：评审附件绑定表（内容寻址附件 → 评审引用）。

Revision ID: 0002_m1_review_attachments
Revises: 0001_m0_initial
Create Date: 2026-11-10

- 附件文件仍按 sha256 内容寻址（`attachments`）；
- `review_attachments` 记录某次评审引用了哪些附件，删除评审时级联删除绑定，物理文件保留给其他引用；
- `issues` 投影表在 0001 已建立，本版本不改变其结构。
"""

from __future__ import annotations

from alembic import op

revision = "0002_m1_review_attachments"
down_revision = "0001_m0_initial"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    CREATE TABLE review_attachments (
        review_id     UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        attachment_id UUID NOT NULL REFERENCES attachments(id) ON DELETE RESTRICT,
        file_name     TEXT NOT NULL,
        sha256        TEXT NOT NULL,
        status        TEXT NOT NULL DEFAULT 'ready'
                      CHECK (status IN ('pending','ready','deleted')),
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (review_id, attachment_id)
    )
    """,
    "CREATE INDEX idx_review_attachments_attachment ON review_attachments (attachment_id)",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS review_attachments",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
