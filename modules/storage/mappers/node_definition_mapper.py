from __future__ import annotations

from common_schemas.enums import RiskLevel
from nodes_graph.domain.entities.node_definition import NodeDefinition

from ..orm.node_definition_model import NodeDefinitionModel


class NodeDefinitionMapper:
    @staticmethod
    def to_domain(orm: NodeDefinitionModel) -> NodeDefinition:
        return NodeDefinition(
            node_id=orm.node_id,
            node_type=orm.node_type,
            name=orm.name,
            category=orm.category,
            version=orm.version,
            input_schema=orm.input_schema,
            output_schema=orm.output_schema,
            parameter_schema=orm.parameter_schema,
            risk_level=RiskLevel(orm.risk_level),
            required_connections=list(orm.required_connections),
            description=orm.description,
            is_mvp=orm.is_mvp,
            service_type=orm.service_type,
            embedding=list(orm.embedding) if orm.embedding is not None else None,
            owner_user_id=orm.owner_user_id,
            team_id=orm.team_id,
        )

    @staticmethod
    def to_orm(entity: NodeDefinition) -> NodeDefinitionModel:
        return NodeDefinitionModel(
            node_id=entity.node_id,
            node_type=entity.node_type,
            name=entity.name,
            category=entity.category,
            version=entity.version,
            input_schema=entity.input_schema,
            output_schema=entity.output_schema,
            parameter_schema=entity.parameter_schema,
            risk_level=entity.risk_level.value if isinstance(entity.risk_level, RiskLevel) else entity.risk_level,
            required_connections=list(entity.required_connections),
            description=entity.description,
            is_mvp=entity.is_mvp,
            service_type=entity.service_type,
            embedding=entity.embedding,
            owner_user_id=entity.owner_user_id,
            team_id=entity.team_id,
        )
