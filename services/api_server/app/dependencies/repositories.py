from __future__ import annotations

from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from fastapi import Depends
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository
from skills_marketplace.domain.ports.skill_repository import SkillRepository
from sqlalchemy.ext.asyncio import AsyncSession
from storage.repositories.pg_execution_repository import PgExecutionRepository
from storage.repositories.pg_marketplace_skill_repository import PgMarketplaceSkillRepository
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


def get_marketplace_skill_repository(
    session: AsyncSession = Depends(get_db),
) -> SkillRepository:
    return PgMarketplaceSkillRepository(session)


def get_execution_repository(
    session: AsyncSession = Depends(get_db),
) -> PgExecutionRepository:
    return PgExecutionRepository(session)
