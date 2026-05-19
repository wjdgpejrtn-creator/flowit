-- 018_executions_celery_task_id.sql
-- Add celery_task_id column to executions table.
-- Required for REQ-007 ExecutionRepository.cancel — Celery worker.control.revoke()
-- needs the task_id captured when api_server dispatches the workflow execution.
--
-- ADR-0011: IF NOT EXISTS 멱등 + schema_migrations 추적 대상.
-- migration_runner는 declared_tables 기반 backfill을 사용하므로 ALTER-only
-- 파일은 항상 실 apply 경로로 들어간다 (정상).

ALTER TABLE executions
    ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(155);

CREATE INDEX IF NOT EXISTS idx_executions_celery_task_id
    ON executions(celery_task_id)
    WHERE celery_task_id IS NOT NULL;

COMMENT ON COLUMN executions.celery_task_id IS
    'Celery AsyncResult.id of the dispatched execute_workflow task. '
    'Populated by execute_workflow_task (self.request.id) on pickup. '
    'Used by cancel_execution_task → celery_app.control.revoke(task_id, terminate=True).';
