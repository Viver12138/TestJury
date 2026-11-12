"""Fenced, immutable stage outputs for restart recovery."""
from alembic import op

revision = "0006_stage_checkpoints"
down_revision = "0005_m2_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stage_checkpoints (
        review_id UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        stage_key TEXT NOT NULL, input_digest TEXT NOT NULL,
        output_digest TEXT NOT NULL, payload JSONB NOT NULL,
        fencing_token BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (review_id, stage_key, input_digest))""")
    op.execute("""CREATE FUNCTION checkpoint_no_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'checkpoint output is immutable'; END $$""")
    op.execute("""CREATE TRIGGER checkpoint_no_update BEFORE UPDATE ON stage_checkpoints
                  FOR EACH ROW EXECUTE FUNCTION checkpoint_no_update()""")


def downgrade() -> None:
    op.execute("DROP TABLE stage_checkpoints")
    op.execute("DROP FUNCTION checkpoint_no_update()")
