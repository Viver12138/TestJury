"""Immutable knowledge builds, vector index and atomic active pointers."""

from alembic import op

revision = "0005_m2_knowledge"
down_revision = "0004_m1_masking_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE knowledge_builds (
        version TEXT PRIMARY KEY, project_id TEXT NOT NULL, baseline TEXT NOT NULL,
        payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE knowledge_vectors (
        version TEXT NOT NULL REFERENCES knowledge_builds(version), chunk_id TEXT NOT NULL,
        embedding vector(1024) NOT NULL, PRIMARY KEY(version, chunk_id))""")
    op.execute("CREATE INDEX knowledge_vectors_hnsw ON knowledge_vectors USING hnsw (embedding vector_cosine_ops)")
    op.execute("""CREATE TABLE knowledge_active (
        project_id TEXT NOT NULL, baseline TEXT NOT NULL,
        version TEXT NOT NULL REFERENCES knowledge_builds(version), PRIMARY KEY(project_id, baseline))""")
    op.execute("""CREATE TABLE knowledge_events (
        id BIGSERIAL PRIMARY KEY, project_id TEXT NOT NULL, version TEXT NOT NULL REFERENCES knowledge_builds(version),
        previous TEXT, actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    op.execute("""CREATE FUNCTION knowledge_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'knowledge history is immutable'; END $$""")
    for table in ("knowledge_builds", "knowledge_vectors", "knowledge_events"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION knowledge_immutable()")


def downgrade() -> None:
    for table in ("knowledge_events", "knowledge_active", "knowledge_vectors", "knowledge_builds"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION knowledge_immutable()")
