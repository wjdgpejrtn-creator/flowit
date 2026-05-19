"""ExecutionRepository 구현체.

Port ABC 위치: execution_engine.domain.ports.ExecutionRepositoryPort (아직 미생성)
ABC 생성 시 상속 추가 예정.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
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
