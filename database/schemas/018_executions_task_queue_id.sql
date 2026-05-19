-- 018_executions_task_queue_id.sql
-- Add task_queue_id column to executions table.
-- Required for REQ-007 cancel/resume — `TaskQueuePort.revoke(task_id)` (CeleryAdapter
-- backend → `app.control.revoke()`) needs the task_id captured when api_server
-- dispatches the workflow execution. Column name intentionally framework-agnostic
-- (not "celery_task_id") so a future broker swap (Celery → other) needs only the
-- adapter change, not a DDL migration.
--
-- ADR-0011: IF NOT EXISTS 멱등 + schema_migrations 추적 대상.
-- migration_runner는 declared_tables 기반 backfill을 사용하므로 ALTER-only
-- 파일은 항상 실 apply 경로로 들어간다 (정상).
--
-- Backfill 운영 영향:
--   머지 시점에 status IN ('running', 'paused')인 기존 row는 task_queue_id NULL이
--   유지된다. 그 행들은 본 PR 머지 이후 cancel 시도해도 revoke 호출이 skip되며
--   (DB는 CANCELLED 마킹만), 워커가 자체 종료되거나 timeout으로 정리되어야 한다.
--   staging은 진행 중 execution이 없는 시점에 적용 권장.

ALTER TABLE executions
    ADD COLUMN IF NOT EXISTS task_queue_id VARCHAR(155);

CREATE INDEX IF NOT EXISTS idx_executions_task_queue_id
    ON executions(task_queue_id)
    WHERE task_queue_id IS NOT NULL;

COMMENT ON COLUMN executions.task_queue_id IS
    'Background task queue id (Celery AsyncResult.id under the current adapter). '
    'Populated by execute_workflow_task on pickup and used by cancel_execution_task '
    'to invoke TaskQueuePort.revoke(). Framework-agnostic name so swapping the queue '
    'backend touches only the adapter, not this schema.';
