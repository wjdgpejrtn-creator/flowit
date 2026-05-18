from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository
from storage.repositories.pg_node_definition_repository import PgNodeDefinitionRepository

from app.dependencies.database import get_db


def get_node_definition_repository(
    session: AsyncSession = Depends(get_db),
) -> NodeDefinitionRepository:
    return PgNodeDefinitionRepository(session)
