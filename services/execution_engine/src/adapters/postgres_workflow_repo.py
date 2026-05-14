from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text

from common_schemas.enums import RiskLevel
from common_schemas.exceptions import NotFoundError
from common_schemas.workflow import (
    Edge,
    NodeConfig,
    NodeInstance,
    WorkflowSchema,
)

from ..domain.ports.workflow_repository_port import WorkflowRepositoryPort

logger = logging.getLogger(__name__)


class PostgresWorkflowRepository(WorkflowRepositoryPort):

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def get(self, workflow_id: UUID) -> WorkflowSchema:
        with self._session_factory() as session:
            row = session.execute(
                text("SELECT * FROM workflows WHERE workflow_id = :wid"),
                {"wid": str(workflow_id)},
            ).mappings().first()

        if row is None:
            raise NotFoundError(f"Workflow {workflow_id} not found")

        nodes = [NodeInstance.model_validate(n) for n in row["nodes"]]
        connections = [Edge.model_validate(e) for e in row["connections"]]

        return WorkflowSchema(
            workflow_id=UUID(row["workflow_id"]),
            name=row["name"],
            scope=row["scope"],
            is_draft=row["is_draft"],
            nodes=nodes,
            connections=connections,
        )

    def get_node_config(self, node_id: UUID) -> NodeConfig:
        with self._session_factory() as session:
            row = session.execute(
                text("SELECT * FROM node_definitions WHERE node_id = :nid"),
                {"nid": str(node_id)},
            ).mappings().first()

        if row is None:
            raise NotFoundError(f"NodeConfig {node_id} not found")

        return NodeConfig(
            node_id=UUID(row["node_id"]),
            node_type=row["node_type"],
            name=row["name"],
            category=row["category"],
            version=row["version"],
            input_schema=row["input_schema"],
            output_schema=row["output_schema"],
            parameter_schema=row["parameter_schema"],
            risk_level=RiskLevel(row["risk_level"]),
            required_connections=row["required_connections"],
            description=row["description"],
            is_mvp=row["is_mvp"],
        )
