from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from common_schemas import NodeConfig, WorkflowSchema
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import NotFoundError

from ..mappers.workflow_mapper import WorkflowMapper
from ..orm.workflow_model import WorkflowModel


class PgWorkflowRepository(WorkflowRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, workflow: WorkflowSchema) -> UUID:
        model = WorkflowMapper.to_orm(workflow)
        merged = await self._session.merge(model)
        await self._session.flush()
        return merged.workflow_id

    async def find_by_id(self, workflow_id: UUID) -> Optional[WorkflowSchema]:
        stmt = select(WorkflowModel).where(WorkflowModel.workflow_id == workflow_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return WorkflowMapper.to_domain(model)

    async def list_by_owner(
        self,
        owner_user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowSchema]:
        stmt = (
            select(WorkflowModel)
            .where(WorkflowModel.user_id == owner_user_id)
            .order_by(WorkflowModel.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [WorkflowMapper.to_domain(m) for m in result.scalars().all()]

    async def get_node_config(self, node_id: UUID) -> NodeConfig:
        from ..orm.node_definition_model import NodeDefinitionModel

        stmt = select(NodeDefinitionModel).where(NodeDefinitionModel.node_id == node_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise NotFoundError(f"Node config not found: {node_id}", code="E-NODE-001")
        return NodeConfig(
            node_id=model.node_id,
            node_type=model.node_type,
            name=model.name,
            category=model.category,
            version=model.version,
            input_schema=model.input_schema,
            output_schema=model.output_schema,
            parameter_schema=model.parameter_schema,
            risk_level=RiskLevel(model.risk_level),
            required_connections=list(model.required_connections),
            description=model.description,
            is_mvp=model.is_mvp,
        )
