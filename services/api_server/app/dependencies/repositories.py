from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository
from storage.repositories.pg_node_definition_repository import PgNodeDefinitionRepository
from storage.repositories.pg_workflow_repository import PgWorkflowRepository

from app.dependencies.database import get_db


def get_node_definition_repository(
    session: AsyncSession = Depends(get_db),
) -> NodeDefinitionRepository:
    return PgNodeDefinitionRepository(session)


def get_workflow_repository(
    session: AsyncSession = Depends(get_db),
) -> WorkflowRepository:
    return PgWorkflowRepository(session)
