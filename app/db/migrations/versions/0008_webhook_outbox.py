"""Durable terminal-event delivery with leases and bounded retries."""
from alembic import op

revision = "0008_webhook_outbox"
down_revision = "0007_model_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE webhook_deliveries (
        event_id TEXT PRIMARY KEY, review_id UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        url TEXT NOT NULL, payload JSONB NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','delivered','failed')),
        attempts INT NOT NULL DEFAULT 0, next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        lease_until TIMESTAMPTZ, last_error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX webhook_pending ON webhook_deliveries(status,next_attempt_at)")


def downgrade() -> None:
    op.execute("DROP TABLE webhook_deliveries")
