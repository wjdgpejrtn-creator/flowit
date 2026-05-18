from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from common_schemas import NodeConfig
from common_schemas import PermissionSource
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_node_definition_repository

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])


def _to_node_config(d: NodeDefinition) -> NodeConfig:
    """NodeDefinition(dataclass, embedding 포함) → NodeConfig(Pydantic, SSOT) 변환.

    embedding(768차원)은 응답 페이로드 부담이라 제외. service_type도 NodeConfig 미정의 — 제외.
    필요 시 후속에서 NodeConfig 확장 또는 별도 응답 모델.
    """
    return NodeConfig(
        node_id=d.node_id,
        node_type=d.node_type,
        name=d.name,
        category=d.category,
        version=d.version,
        input_schema=d.input_schema,
        output_schema=d.output_schema,
        parameter_schema=d.parameter_schema,
        risk_level=d.risk_level,
        required_connections=d.required_connections,
        description=d.description,
        is_mvp=d.is_mvp,
    )


@router.get("/catalog", response_model=list[NodeConfig])
async def get_catalog(
    mvp_only: bool = Query(False, description="True면 is_mvp=True 노드만 반환"),
    repo: NodeDefinitionRepository = Depends(get_node_definition_repository),
    _permission: PermissionSource = Depends(get_permission_source),  # 인증 보장
) -> list[NodeConfig]:
    definitions = await repo.list_all(mvp_only=mvp_only)
    return [_to_node_config(d) for d in definitions]
