"""M0 初始 Schema：评审任务、阶段、候选、投票、报告决定、复核任务、审计、授权表。

Revision ID: 0001_m0_initial
Revises:
Create Date: 2026-11-10

说明：
- 枚举 CHECK 与 docs/17 对齐；JSONB 结构由应用层校验；
- `review_jobs` 部分唯一索引保证同一幂等键只有一个 active 代次；
- `report_locked_at` 非空后，报告字段与 ai_verdict 不允许 UPDATE（触发器兜底）；
- 附件表为 v1 内容寻址实现（同一 sha256 只存一份），随评审删除。
"""

from __future__ import annotations

from alembic import op

revision = "0001_m0_initial"
down_revision = None
branch_labels = None
depends_on = None

STAGE_CHECK = (
    "'input_check','preprocess','kb_retrieve','blind_review','fusion','vote',"
    "'arbitration','verdict','render'"
)

UPGRADE: list[str] = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    """
    CREATE TABLE api_keys (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        key_hash        TEXT NOT NULL UNIQUE,
        actor_id        TEXT NOT NULL,
        actor_type      TEXT NOT NULL CHECK (actor_type IN ('service','human')),
        roles           TEXT[] NOT NULL DEFAULT '{}',
        caller_id       TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        revoked_at      TIMESTAMPTZ,
        expires_at      TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE batches (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        status          TEXT NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','processing','completed','partially_completed','failed','cancelled')),
        total           INT NOT NULL DEFAULT 0 CHECK (total >= 0),
        done            INT NOT NULL DEFAULT 0 CHECK (done >= 0),
        failed          INT NOT NULL DEFAULT 0 CHECK (failed >= 0),
        caller_id       TEXT,
        input_hash      TEXT,
        idempotency_key TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at     TIMESTAMPTZ
    )
    """,
    "CREATE UNIQUE INDEX uq_batches_idempotency ON batches (idempotency_key) WHERE idempotency_key IS NOT NULL",
    f"""
    CREATE TABLE review_jobs (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        batch_id              UUID REFERENCES batches(id) ON DELETE SET NULL,
        case_id               TEXT NOT NULL,
        case_title            TEXT,
        case_version          INT NOT NULL DEFAULT 1 CHECK (case_version >= 1),
        module                TEXT,
        test_type             TEXT NOT NULL
                              CHECK (test_type IN ('functional','performance','security','compatibility','reliability','usability','other')),
        test_type_source      TEXT NOT NULL DEFAULT 'request'
                              CHECK (test_type_source IN ('request','compat_default')),
        status                TEXT NOT NULL DEFAULT 'queued'
                              CHECK (status IN ('queued','processing','retrying','done','completed_with_warnings','failed','cancelled')),
        stage                 TEXT CHECK (stage IS NULL OR stage IN ({STAGE_CHECK})),
        ai_verdict            TEXT CHECK (ai_verdict IS NULL OR ai_verdict IN ('blocked','conditional','need_human')),
        human_status          TEXT NOT NULL DEFAULT 'pending'
                              CHECK (human_status IN ('pending','approved','rejected','changes_requested')),
        current_decision_id   TEXT,
        degraded              BOOLEAN NOT NULL DEFAULT FALSE,
        degraded_reasons      JSONB NOT NULL DEFAULT '[]'::jsonb,
        participants          JSONB NOT NULL DEFAULT '[]'::jsonb,
        topology              TEXT NOT NULL DEFAULT 'multi' CHECK (topology IN ('single','dual','multi')),
        topology_snapshot     JSONB,
        review_completeness   JSONB,
        input_quality         JSONB,
        timings               JSONB,
        test_scope            JSONB,
        automation_context    JSONB,
        kb_content_version    TEXT,
        kb_build_version      TEXT,
        rubric_version        TEXT,
        prompt_versions       JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        prompt_version_hash   TEXT NOT NULL,
        retrieval_config_version TEXT,
        embedding_profile_id  BIGINT,
        reranker_profile_id   BIGINT,
        model_config_version  TEXT,
        report_schema_version TEXT NOT NULL,
        input_hash            TEXT NOT NULL,
        idempotency_key       TEXT NOT NULL,
        generation            INT NOT NULL DEFAULT 1 CHECK (generation >= 1),
        parent_review_id      UUID REFERENCES review_jobs(id),
        superseded_by         UUID REFERENCES review_jobs(id),
        request_payload       JSONB NOT NULL,
        normalized_case       JSONB,
        report_summary        JSONB,
        report_json           JSONB,
        report_locked_at      TIMESTAMPTZ,
        error                 TEXT,
        total_cost_estimate   NUMERIC(12,4),
        cost_currency         TEXT DEFAULT 'CNY',
        attempt_count         INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        max_attempts          INT NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
        locked_by             TEXT,
        locked_at             TIMESTAMPTZ,
        lease_expires_at      TIMESTAMPTZ,
        fencing_token         BIGINT NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
        last_error            TEXT,
        submitter_id          TEXT,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
        started_at            TIMESTAMPTZ,
        finished_at           TIMESTAMPTZ
    )
    """,
    "CREATE UNIQUE INDEX uq_review_jobs_idempotency ON review_jobs (idempotency_key) WHERE superseded_by IS NULL",
    "CREATE INDEX idx_review_jobs_case ON review_jobs (case_id, created_at DESC)",
    "CREATE INDEX idx_review_jobs_module ON review_jobs (module, created_at DESC)",
    "CREATE INDEX idx_review_jobs_verdict ON review_jobs (ai_verdict, human_status, created_at DESC)",
    "CREATE INDEX idx_review_jobs_batch ON review_jobs (batch_id)",
    "CREATE INDEX idx_review_jobs_queue ON review_jobs (status, lease_expires_at, created_at) "
    "WHERE status IN ('queued','processing','retrying')",
    """
    CREATE FUNCTION prevent_locked_report_update() RETURNS trigger AS $$
    BEGIN
        IF OLD.report_locked_at IS NOT NULL AND (
            NEW.report_json IS DISTINCT FROM OLD.report_json
            OR NEW.report_summary IS DISTINCT FROM OLD.report_summary
            OR NEW.ai_verdict IS DISTINCT FROM OLD.ai_verdict
        ) THEN
            RAISE EXCEPTION 'report_locked: 报告已锁定，更正必须新建 generation';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "CREATE TRIGGER trg_review_jobs_report_lock BEFORE UPDATE ON review_jobs "
    "FOR EACH ROW EXECUTE FUNCTION prevent_locked_report_update()",
    """
    CREATE TABLE review_participants (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        review_id       UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        participant_id  TEXT NOT NULL,
        role_id         TEXT NOT NULL,
        provider        TEXT,
        model           TEXT,
        model_version   TEXT,
        requested_model TEXT,
        actual_model    TEXT,
        fallback_reason TEXT,
        status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','failed','absent')),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (review_id, participant_id)
    )
    """,
    """
    CREATE TABLE model_runs (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        review_id         UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        role              TEXT NOT NULL,
        provider          TEXT,
        model             TEXT NOT NULL,
        requested_model   TEXT,
        model_version     TEXT,
        prompt_version    TEXT,
        attempt           INT NOT NULL DEFAULT 1,
        status            TEXT NOT NULL CHECK (status IN ('ok','timeout','error','parse_error')),
        request_tokens    INT,
        response_tokens   INT,
        latency_ms        INT,
        raw_request       JSONB,
        raw_response      JSONB,
        parsed_output     JSONB,
        parse_warnings    JSONB NOT NULL DEFAULT '[]'::jsonb,
        cost_estimate     NUMERIC(12,4),
        cost_currency     TEXT DEFAULT 'CNY',
        price_config_version TEXT,
        error             TEXT,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    f"""
    CREATE TABLE review_stages (
        id            BIGSERIAL PRIMARY KEY,
        review_id     UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        stage         TEXT NOT NULL CHECK (stage IN ({STAGE_CHECK})),
        status        TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','running','succeeded','failed','skipped')),
        attempt       INT NOT NULL DEFAULT 1 CHECK (attempt >= 0),
        fencing_token BIGINT,
        input_digest  TEXT,
        output_ref    TEXT,
        started_at    TIMESTAMPTZ,
        finished_at   TIMESTAMPTZ,
        error         TEXT,
        UNIQUE (review_id, stage)
    )
    """,
    f"""
    CREATE TABLE review_stage_attempts (
        id            BIGSERIAL PRIMARY KEY,
        review_id     UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        stage         TEXT NOT NULL CHECK (stage IN ({STAGE_CHECK})),
        attempt_no    INT NOT NULL CHECK (attempt_no >= 1),
        fencing_token BIGINT,
        status        TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','skipped')),
        input_digest  TEXT,
        output_ref    TEXT,
        started_at    TIMESTAMPTZ,
        finished_at   TIMESTAMPTZ,
        error_code    TEXT,
        error_message TEXT,
        worker_id     TEXT,
        model_run_id  UUID REFERENCES model_runs(id),
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (review_id, stage, attempt_no)
    )
    """,
    """
    CREATE TABLE review_candidates (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        review_id         UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        candidate_no      INT NOT NULL CHECK (candidate_no >= 1),
        step_index        INT,
        dimension         TEXT NOT NULL CHECK (dimension IN ('business','test_design','automation')),
        severity_proposal TEXT CHECK (severity_proposal IS NULL OR severity_proposal IN ('blocker','major','suggestion')),
        standardized_text TEXT NOT NULL,
        claims            JSONB NOT NULL DEFAULT '[]'::jsonb,
        evidence_status   TEXT NOT NULL DEFAULT 'insufficient'
                          CHECK (evidence_status IN ('grounded','partially_grounded','ungrounded','conflicted','insufficient')),
        vote_valid_count  INT NOT NULL DEFAULT 0 CHECK (vote_valid_count >= 0),
        vote_completeness TEXT CHECK (vote_completeness IS NULL OR vote_completeness IN ('3/3','2/3','1/3','0/3')),
        evidence_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,
        proposed_by       JSONB NOT NULL DEFAULT '[]'::jsonb,
        merged_from       JSONB NOT NULL DEFAULT '[]'::jsonb,
        fusion_basis      JSONB,
        status            TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','disputed','merged')),
        category          TEXT,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (review_id, candidate_no),
        UNIQUE (id, review_id)
    )
    """,
    """
    CREATE TABLE issues (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        review_id         UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        candidate_id      UUID,
        issue_no          INT NOT NULL CHECK (issue_no >= 1),
        step_index        INT,
        step_tolerance    INT NOT NULL DEFAULT 1,
        dimension         TEXT NOT NULL CHECK (dimension IN ('business','test_design','automation')),
        severity          TEXT NOT NULL CHECK (severity IN ('blocker','major','suggestion')),
        category          TEXT NOT NULL,
        evidence_quote    TEXT,
        rationale         TEXT NOT NULL,
        suggestion        TEXT,
        kb_grounded       BOOLEAN NOT NULL DEFAULT FALSE,
        kb_refs           JSONB NOT NULL DEFAULT '[]'::jsonb,
        evidence_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,
        evidence_type     TEXT,
        evidence_strength TEXT,
        evidence_status   TEXT,
        proposed_by       JSONB NOT NULL DEFAULT '[]'::jsonb,
        merged_from       JSONB NOT NULL DEFAULT '[]'::jsonb,
        fusion_basis      JSONB,
        support_count     INT NOT NULL DEFAULT 0,
        reject_count      INT NOT NULL DEFAULT 0,
        not_assessed_count INT NOT NULL DEFAULT 0,
        uncertain_count   INT NOT NULL DEFAULT 0,
        support_ratio     NUMERIC(3,2),
        severity_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
        confidence        NUMERIC(3,2),
        confidence_source TEXT NOT NULL DEFAULT 'uncalibrated',
        model_confidence  NUMERIC(3,2),
        validation_status TEXT,
        evidence_support_status TEXT,
        decision_status   TEXT,
        status            TEXT NOT NULL
                          CHECK (status IN ('adopted','rejected','disputed','need_human','chief_supplement')),
        chief_decision    TEXT CHECK (chief_decision IS NULL OR chief_decision IN ('adopt','reject','dispute','need_human','supplement')),
        chief_reason      TEXT,
        human_verdict     TEXT,
        human_note        TEXT,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (review_id, issue_no),
        UNIQUE (id, review_id),
        UNIQUE (review_id, candidate_id)
    )
    """,
    """
    ALTER TABLE issues
        ADD CONSTRAINT fk_issue_candidate_review
        FOREIGN KEY (candidate_id, review_id)
        REFERENCES review_candidates (id, review_id)
    """,
    """
    CREATE TABLE issue_votes (
        id            BIGSERIAL PRIMARY KEY,
        candidate_id  UUID NOT NULL,
        issue_id      UUID REFERENCES issues(id),
        review_id     UUID NOT NULL,
        model_run_id  UUID REFERENCES model_runs(id),
        reviewer_id   TEXT NOT NULL,
        validity      TEXT NOT NULL CHECK (validity IN ('accept','reject','uncertain','not_assessed')),
        severity      TEXT CHECK (severity IS NULL OR severity IN ('blocker','major','suggestion')),
        reason        TEXT,
        evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (candidate_id, reviewer_id),
        CHECK (validity = 'accept' OR severity IS NULL)
    )
    """,
    """
    ALTER TABLE issue_votes
        ADD CONSTRAINT fk_vote_candidate
        FOREIGN KEY (candidate_id, review_id)
        REFERENCES review_candidates (id, review_id)
    """,
    """
    CREATE TABLE review_decisions (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        review_id             UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        decision_no           BIGSERIAL,
        decision              TEXT NOT NULL CHECK (decision IN ('approve','reject','request_changes')),
        reviewer_id           TEXT NOT NULL,
        reason                TEXT,
        previous_verdict      TEXT,
        previous_human_status TEXT,
        report_schema_version TEXT NOT NULL,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK (decision = 'approve' OR reason IS NOT NULL)
    )
    """,
    "CREATE INDEX idx_review_decisions_review ON review_decisions (review_id, decision_no DESC)",
    """
    CREATE TABLE human_review_tasks (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        review_id    UUID NOT NULL REFERENCES review_jobs(id) ON DELETE CASCADE,
        issue_id     UUID REFERENCES issues(id),
        review_level TEXT NOT NULL CHECK (review_level IN ('issue','report')),
        priority     TEXT NOT NULL DEFAULT 'normal'
                     CHECK (priority IN ('blocker','severity_disputed','evidence_conflict','normal')),
        assignee     TEXT,
        status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','in_progress','completed','cancelled')),
        result       TEXT CHECK (result IS NULL OR result IN ('confirmed','rejected','modified','insufficient_information','escalated')),
        reason       TEXT,
        source       TEXT NOT NULL DEFAULT 'auto' CHECK (source IN ('auto','manual')),
        due_at       TIMESTAMPTZ,
        version      INT NOT NULL DEFAULT 0 CHECK (version >= 0),
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        started_at   TIMESTAMPTZ,
        handled_at   TIMESTAMPTZ,
        CHECK (review_level = 'issue' OR result IS NULL),
        CHECK (result IS NULL OR reason IS NOT NULL)
    )
    """,
    """
    CREATE TABLE human_review_events (
        id         BIGSERIAL PRIMARY KEY,
        task_id    UUID NOT NULL REFERENCES human_review_tasks(id) ON DELETE CASCADE,
        action     TEXT NOT NULL,
        actor      TEXT NOT NULL,
        reason     TEXT,
        payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE audit_log (
        id         BIGSERIAL PRIMARY KEY,
        event_type TEXT NOT NULL,
        actor      TEXT,
        review_id  UUID,
        payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX idx_audit_log_review ON audit_log (review_id, created_at DESC)",
    """
    CREATE TABLE attachments (
        id           UUID PRIMARY KEY,
        file_name    TEXT NOT NULL,
        mime_type    TEXT NOT NULL,
        size_bytes   BIGINT NOT NULL CHECK (size_bytes >= 0),
        sha256       TEXT NOT NULL UNIQUE,
        storage_uri  TEXT NOT NULL,
        storage_path TEXT,
        uploader_id  TEXT,
        status       TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('pending','ready','deleted')),
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]

DOWNGRADE: list[str] = [
    "DROP TRIGGER IF EXISTS trg_review_jobs_report_lock ON review_jobs",
    "DROP FUNCTION IF EXISTS prevent_locked_report_update()",
    "DROP TABLE IF EXISTS attachments",
    "DROP TABLE IF EXISTS audit_log",
    "DROP TABLE IF EXISTS human_review_events",
    "DROP TABLE IF EXISTS human_review_tasks",
    "DROP TABLE IF EXISTS review_decisions",
    "DROP TABLE IF EXISTS issue_votes",
    "DROP TABLE IF EXISTS issues",
    "DROP TABLE IF EXISTS review_candidates",
    "DROP TABLE IF EXISTS review_stage_attempts",
    "DROP TABLE IF EXISTS review_stages",
    "DROP TABLE IF EXISTS model_runs",
    "DROP TABLE IF EXISTS review_participants",
    "DROP TABLE IF EXISTS review_jobs",
    "DROP TABLE IF EXISTS batches",
    "DROP TABLE IF EXISTS api_keys",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
