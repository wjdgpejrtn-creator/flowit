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

        # pg8000은 PostgreSQL UUID 컬럼을 이미 uuid.UUID 객체로 반환한다.
        # UUID(UUID객체)는 생성자가 hex str로 간주해 .replace() 호출 → AttributeError.
        # str()을 거쳐 pg8000(UUID 반환)/psycopg2(str 반환) 양쪽에서 안전하게 파싱.
        owner_user_id_raw = row.get("user_id")
        return WorkflowSchema(
            workflow_id=UUID(str(row["workflow_id"])),
            owner_user_id=UUID(str(owner_user_id_raw)) if owner_user_id_raw else None,
            name=row["name"],
            description=row.get("description"),
            scope=row["scope"],
            is_draft=row["is_draft"],
            nodes=nodes,
            connections=connections,
            version=row.get("version"),
            sha256=row.get("sha256"),
            created_via_session_id=UUID(str(row["created_via_session_id"]))
                if row.get("created_via_session_id")
                else None,
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
            node_id=UUID(str(row["node_id"])),
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
