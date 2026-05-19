from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import NotFoundError
from common_schemas.workflow import NodeExecutionState

from ..domain.entities.execution_result import ExecutionResult, NodeResult
from ..domain.ports.execution_repository_port import ExecutionRepositoryPort

logger = logging.getLogger(__name__)


class PostgresExecutionRepository(ExecutionRepositoryPort):

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def save(self, result: ExecutionResult) -> None:
        # DB schema(001_core.sql executions.user_id NOT NULL) 방어 — Optional 도메인 필드를
        # raw SQL INSERT 시점에서 명시 ValueError로 전환. modules/storage mapper와 동일 패턴.
        if result.user_id is None:
            raise ValueError(
                "ExecutionResult.user_id is required for DB persistence "
                "(executions.user_id NOT NULL). Set user_id in the use case "
                "before calling Repository.save()."
            )
        data = result.model_dump(mode="json")
        with self._session_factory() as session:
            session.execute(
                text("""
                    INSERT INTO executions
                        (execution_id, workflow_id, user_id, status, node_results,
                         started_at, completed_at, error)
                    VALUES
                        (:execution_id, :workflow_id, :user_id, :status, :node_results,
                         :started_at, :completed_at, :error)
                    ON CONFLICT (execution_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        node_results = EXCLUDED.node_results,
                        completed_at = EXCLUDED.completed_at,
                        error = EXCLUDED.error
                """),
                {
                    "execution_id": data["execution_id"],
                    "workflow_id": data["workflow_id"],
                    "user_id": data["user_id"],
                    "status": data["status"],
                    "node_results": json.dumps(data["node_results"]),
                    "started_at": data["started_at"],
                    "completed_at": data["completed_at"],
                    "error": data["error"],
                },
            )
            session.commit()

    def get(self, execution_id: UUID) -> ExecutionResult:
        with self._session_factory() as session:
            row = session.execute(
                text("SELECT * FROM executions WHERE execution_id = :eid"),
                {"eid": str(execution_id)},
            ).mappings().first()

        if row is None:
            raise NotFoundError(f"ExecutionResult {execution_id} not found")

        node_results_raw = row["node_results"]
        if isinstance(node_results_raw, str):
            node_results_raw = json.loads(node_results_raw)

        user_id_raw = row.get("user_id")
        return ExecutionResult(
            execution_id=UUID(row["execution_id"]),
            workflow_id=UUID(row["workflow_id"]),
            user_id=UUID(user_id_raw) if user_id_raw else None,
            status=ExecutionStatus(row["status"]),
            node_results=[NodeResult.model_validate(nr) for nr in node_results_raw],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error=row["error"],
        )

    def update_node_state(self, execution_id: UUID, state: NodeExecutionState) -> None:
        state_data = state.model_dump(mode="json")
        with self._session_factory() as session:
            session.execute(
                text("""
                    INSERT INTO node_execution_states
                        (execution_id, node_instance_id, status, attempt, last_error)
                    VALUES
                        (:execution_id, :node_instance_id, :status, :attempt, :last_error)
                    ON CONFLICT (execution_id, node_instance_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        attempt = EXCLUDED.attempt,
                        last_error = EXCLUDED.last_error,
                        updated_at = NOW()
                """),
                {
                    "execution_id": str(execution_id),
                    "node_instance_id": state_data["node_instance_id"],
                    "status": state_data["status"],
                    "attempt": state_data["attempt"],
                    "last_error": state_data["last_error"],
                },
            )
            session.commit()
