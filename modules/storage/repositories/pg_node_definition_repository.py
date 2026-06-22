from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.node_definition_repository import (
    NodeDefinitionRepository,
)

from ..mappers.node_definition_mapper import NodeDefinitionMapper
from ..orm.node_definition_model import NodeDefinitionModel


class PgNodeDefinitionRepository(NodeDefinitionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, definition: NodeDefinition) -> NodeDefinition:
        model = NodeDefinitionMapper.to_orm(definition)
        merged = await self._session.merge(model)
        await self._session.flush()
        return NodeDefinitionMapper.to_domain(merged)

    async def list_all(self, mvp_only: bool = False) -> list[NodeDefinition]:
        stmt = select(NodeDefinitionModel)
        if mvp_only:
            stmt = stmt.where(NodeDefinitionModel.is_mvp.is_(True))
        result = await self._session.execute(stmt)
        return [NodeDefinitionMapper.to_domain(row) for row in result.scalars().all()]

    async def get_by_id(self, node_id: UUID) -> NodeDefinition | None:
        stmt = select(NodeDefinitionModel).where(NodeDefinitionModel.node_id == node_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return NodeDefinitionMapper.to_domain(model)

    async def search_by_embedding(
        self,
        query_embedding: list[float],
        limit: int = 10,
        viewer_user_id: UUID | None = None,
        viewer_team_ids: list[UUID] | None = None,
    ) -> list[NodeDefinition]:
        # ADR-0020 (i) scope 격리. (owner IS NULL AND team IS NULL) = company 전역,
        # owner=viewer = personal, team IN viewer_teams = team.
        # viewer 둘 다 미지정이면 전역 노드만 반환 (비침습 기본).
        visibility = [
            and_(
                NodeDefinitionModel.owner_user_id.is_(None),
                NodeDefinitionModel.team_id.is_(None),
            )
        ]
        if viewer_user_id is not None:
            visibility.append(NodeDefinitionModel.owner_user_id == viewer_user_id)
        if viewer_team_ids:
            visibility.append(NodeDefinitionModel.team_id.in_(viewer_team_ids))

        stmt = (
            select(NodeDefinitionModel)
            .where(NodeDefinitionModel.embedding.isnot(None))
            .where(or_(*visibility))
            .order_by(NodeDefinitionModel.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [NodeDefinitionMapper.to_domain(row) for row in result.scalars().all()]
