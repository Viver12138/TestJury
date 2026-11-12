"""Durable budget reservations, shared by concurrent workers and retries."""
from alembic import op

revision = "0007_model_budget"
down_revision = "0006_stage_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE model_budget_reservations (
        id UUID PRIMARY KEY, review_id UUID REFERENCES review_jobs(id) ON DELETE SET NULL, batch_id UUID,
        budget_day DATE NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')::date,
        model TEXT NOT NULL, tokens_reserved BIGINT NOT NULL CHECK(tokens_reserved>0),
        cost_reserved NUMERIC NOT NULL CHECK(cost_reserved>=0),
        tokens_actual BIGINT, cost_actual NUMERIC,
        status TEXT NOT NULL DEFAULT 'reserved' CHECK(status IN ('reserved','settled')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX budget_day_idx ON model_budget_reservations(budget_day)")
    op.execute("CREATE INDEX budget_review_idx ON model_budget_reservations(review_id)")
    op.execute("CREATE INDEX budget_batch_idx ON model_budget_reservations(batch_id)")
    # Carry forward known historical charges. Unreported provider charges cannot
    # be reconstructed and remain an explicitly documented billing limitation.
    op.execute("""INSERT INTO model_budget_reservations
        (id,review_id,batch_id,budget_day,model,tokens_reserved,cost_reserved,tokens_actual,cost_actual,status,created_at)
        SELECT r.id,r.review_id,j.batch_id,(r.created_at AT TIME ZONE 'UTC')::date,r.model,
               GREATEST(1,COALESCE(r.request_tokens,0)+COALESCE(r.response_tokens,0)),r.cost_estimate,
               COALESCE(r.request_tokens,0)+COALESCE(r.response_tokens,0),r.cost_estimate,'settled',r.created_at
        FROM model_runs r JOIN review_jobs j ON j.id=r.review_id
        WHERE r.status='ok' AND r.cost_estimate IS NOT NULL AND r.cost_estimate>=0""")


def downgrade() -> None:
    op.execute("DROP TABLE model_budget_reservations")
