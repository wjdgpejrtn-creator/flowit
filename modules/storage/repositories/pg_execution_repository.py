"""ExecutionRepository 구현체.

Port ABC 위치: execution_engine.domain.ports.ExecutionRepositoryPort (아직 미생성)
ABC 생성 시 상속 추가 예정.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from common_schemas import NodeExecutionState
from common_schemas.exceptions import NotFoundError

from ..mappers.execution_mapper import ExecutionMapper, ExecutionRow
from ..orm.execution_model import ExecutionModel


class PgExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, result: ExecutionRow) -> None:
        model = ExecutionMapper.to_orm(result)
        merged = await self._session.merge(model)
        await self._session.flush()

    async def get(self, execution_id: UUID) -> ExecutionRow:
        stmt = select(ExecutionModel).where(ExecutionModel.execution_id == execution_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise NotFoundError(f"Execution not found: {execution_id}", code="E-EXEC-001")
        return ExecutionMapper.to_domain(model)

    async def get_latest_by_workflow_id(
        self, workflow_id: UUID, user_id: UUID
    ) -> ExecutionRow | None:
        """워크플로우 + 사용자 기준 가장 최근 execution 1건. 없으면 None.

        `/workflows/{id}` 상세 화면에서 워크플로우 정의 + 마지막 실행 상태를 함께
        보여주기 위한 조회. user_id로 같이 filter — 다른 사용자 실행 노출 방지.
        """
        stmt = (
            select(ExecutionModel)
            .where(ExecutionModel.workflow_id == workflow_id)
            .where(ExecutionModel.user_id == user_id)
            .order_by(ExecutionModel.started_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return ExecutionMapper.to_domain(model)

    async def get_node_states_summary(self, execution_id: UUID) -> dict[str, int]:
        """node_execution_states(017)에서 status별 카운트 집계.

        worker(services/execution_engine/.../postgres_execution_repo.py)가
        update_node_state로 채우는 per-node live state(status: pending/running/
        succeeded/failed/retrying/cancelled). 빈 결과(워커 미진입)는 빈 dict.

        ORM(NodeExecutionStateModel) 미정의 — 단일 집계 쿼리라 raw SQL.
        """
        result = await self._session.execute(
            text(
                "SELECT status, COUNT(*) AS cnt "
                "FROM node_execution_states "
                "WHERE execution_id = :eid "
                "GROUP BY status"
            ),
            {"eid": str(execution_id)},
        )
        return {row.status: int(row.cnt) for row in result}

    async def update_node_state(self, execution_id: UUID, state: NodeExecutionState) -> None:
        stmt = select(ExecutionModel).where(ExecutionModel.execution_id == execution_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise NotFoundError(f"Execution not found: {execution_id}", code="E-EXEC-001")

        state_dict = {
            "node_instance_id": str(state.node_instance_id),
            "status": state.status,
            "attempt": state.attempt,
            "last_error": state.last_error,
        }

        node_results = list(model.node_results)
        for nr in node_results:
            if nr.get("node_instance_id") == str(state.node_instance_id):
                nr.update(state_dict)
                break
        else:
            node_results.append(state_dict)

        stmt_update = (
            update(ExecutionModel)
            .where(ExecutionModel.execution_id == execution_id)
            .values(node_results=node_results)
        )
        await self._session.execute(stmt_update)
